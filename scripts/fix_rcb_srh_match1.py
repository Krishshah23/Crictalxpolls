import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models import db
from models.match import Match
from models.match_standing import MatchStanding
from models.poll import Poll
from models.result import Result
from services.polls import build_standard_polls

TEAM_RCB = "Royal Challengers Bengaluru"
TEAM_SRH = "Sunrisers Hyderabad"


def load_fixture_match_no(match_no: int) -> dict:
    fixtures_path = os.path.join(ROOT, "services", "fixtures_2026.json")
    with open(fixtures_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    for fixture in payload.get("fixtures", []):
        if fixture.get("match_no") == match_no:
            return fixture

    raise SystemExit(f"Fixture match_no {match_no} not found")


def main() -> None:
    fixture = load_fixture_match_no(1)
    start_time = datetime.fromisoformat(fixture["start_time"])
    end_time = start_time + timedelta(hours=4)

    app = app_module.app
    with app.app_context():
        match_66 = Match.query.get(66)
        if not match_66 or {match_66.team_a, match_66.team_b} != {TEAM_RCB, TEAM_SRH}:
            raise SystemExit("Match 66 is not RCB vs SRH as expected")

        match_1 = Match.query.get(1)
        if match_1 and {match_1.team_a, match_1.team_b} != {TEAM_RCB, TEAM_SRH}:
            raise SystemExit("Match id 1 exists but is not RCB vs SRH")

        if not match_1:
            match_1 = Match(
                id=1,
                team_a=fixture["team_a"],
                team_b=fixture["team_b"],
                start_time=start_time,
                end_time=end_time,
                status="completed",
            )
            db.session.add(match_1)
            db.session.flush()

        polls = Poll.query.filter_by(match_id=match_66.id).all()
        for poll in polls:
            poll.match_id = match_1.id

        results = Result.query.filter_by(match_id=match_66.id).all()
        for result in results:
            result.match_id = match_1.id

        standings = MatchStanding.query.filter_by(match_id=match_66.id).all()
        for standing in standings:
            standing.match_id = match_1.id

        match_1.status = "completed"
        match_66.status = "upcoming"

        if Poll.query.filter_by(match_id=match_66.id).count() == 0:
            db.session.add_all(build_standard_polls(match_66))

        db.session.commit()
        print("Updated: match 1 set to completed, match 66 set to upcoming")


if __name__ == "__main__":
    main()
