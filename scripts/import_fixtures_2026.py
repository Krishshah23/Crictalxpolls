import io
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import pdfplumber
import requests

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models import db
from models.match import Match
from models.poll import Poll
from models.result import Result
from models.vote import Vote
from services.ipl_data import TEAMS
from services.polls import build_standard_polls

SCHEDULE_PDF_URL = "https://scores.iplt20.com/TATA%20IPL%202026%20Season%20Schedule.pdf"
OUTPUT_JSON = "services/fixtures_2026.json"

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_line(line: str):
    match = re.match(r"^(\d{1,2})\s+(\d{2}-[A-Z]{3}-\d{2})\s+([A-Za-z]{3})\s+(\d{1,2}:\d{2}\s*[AP]M)\s+(.+)$", line)
    if not match:
        return None

    match_no, date_str, _day, time_str, rest = match.groups()

    home = None
    away = None
    venue = None

    for team in sorted(TEAMS, key=len, reverse=True):
        if rest.startswith(team):
            home = team
            rest = rest[len(team):].strip()
            break

    if not home:
        return None

    for team in sorted(TEAMS, key=len, reverse=True):
        if rest.startswith(team):
            away = team
            rest = rest[len(team):].strip()
            break

    if not away:
        return None

    venue = rest.strip()

    start_local = datetime.strptime(f"{date_str} {time_str}", "%d-%b-%y %I:%M %p").replace(tzinfo=IST)
    start_utc = start_local.astimezone(timezone.utc).replace(tzinfo=None)

    return {
        "match_no": int(match_no),
        "date": date_str,
        "time": time_str,
        "team_a": home,
        "team_b": away,
        "venue": venue,
        "start_time": start_utc.isoformat(),
    }


def load_fixtures():
    response = requests.get(SCHEDULE_PDF_URL, timeout=30)
    response.raise_for_status()

    fixtures = []
    seen = set()

    with pdfplumber.open(io.BytesIO(response.content)) as pdf:
        full_text = " "
        for page in pdf.pages:
            text = page.extract_text() or ""
            full_text += " " + text

    full_text = re.sub(r"\s+", " ", full_text).strip()

    pattern = re.compile(
        r"(\d{1,2})\s+(\d{2}-[A-Z]{3}-\d{2})\s+([A-Z][a-z]{2})\s+(\d{1,2}:\d{2}\s*[AP]M)\s+(.+?)(?=\s+\d{1,2}\s+\d{2}-[A-Z]{3}-\d{2}\s+|$)"
    )

    for match in pattern.finditer(full_text):
        match_no, date_str, day, time_str, rest = match.groups()
        parsed = _parse_line(f"{match_no} {date_str} {day} {time_str} {rest}")
        if not parsed:
            continue
        key = (parsed["match_no"], parsed["team_a"], parsed["team_b"], parsed["start_time"])
        if key in seen:
            continue
        seen.add(key)
        fixtures.append(parsed)

    fixtures.sort(key=lambda item: item["match_no"])
    return fixtures


def write_fixtures_json(fixtures):
    payload = {
        "source": SCHEDULE_PDF_URL,
        "generated_at": datetime.utcnow().isoformat(),
        "fixtures": fixtures,
    }
    with open(OUTPUT_JSON, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def seed_fixtures(fixtures):
    app = app_module.app
    with app.app_context():
        db.session.query(Result).delete()
        db.session.query(Vote).delete()
        db.session.query(Poll).delete()
        db.session.query(Match).delete()
        db.session.commit()

        matches = []
        for fixture in fixtures:
            start = datetime.fromisoformat(fixture["start_time"])
            end = start + timedelta(hours=4)
            match = Match(
                team_a=fixture["team_a"],
                team_b=fixture["team_b"],
                start_time=start,
                end_time=end,
                status="upcoming",
            )
            db.session.add(match)
            db.session.flush()
            db.session.add_all(build_standard_polls(match))
            matches.append(match)

        db.session.commit()
        print(f"Seeded {len(matches)} matches")


def main():
    fixtures = load_fixtures()
    if not fixtures:
        raise SystemExit("No fixtures parsed")
    write_fixtures_json(fixtures)
    seed_fixtures(fixtures)


if __name__ == "__main__":
    main()
