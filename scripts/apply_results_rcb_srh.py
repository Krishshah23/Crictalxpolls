import os
import sys
from datetime import datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models import db
from models.match import Match
from models.poll import Poll
from models.result import Result
from models.vote import Vote
from services.standings import update_match_standings

TEAM_RCB = "Royal Challengers Bengaluru"
TEAM_SRH = "Sunrisers Hyderabad"


def build_answer_key(team_a: str, team_b: str):
    return {
        "Who will win the toss": TEAM_RCB,
        f"{TEAM_SRH} won the toss": "Bowl",
        f"{TEAM_RCB} won the toss": "Bowl",
        f"P1 wickets for {TEAM_SRH}": "1",
        f"P1 runs for {TEAM_SRH}": "61-70",
        f"Highest run scorer for {TEAM_SRH}": "T.Head",
        f"Highest wicket taker for {TEAM_SRH}": "H.Patel",
        f"Economical bowler for {TEAM_SRH}": "J..Unadkat",
        f"How many extras will {TEAM_SRH} give": "11-15",
        f"50's for {TEAM_SRH}": "2",
        f"100 for {TEAM_SRH}": "0",
        f"Projected score for {TEAM_SRH}": "201-220",
        f"P1 wickets for {TEAM_RCB}": "1",
        f"P1 runs for {TEAM_RCB}": "61-70",
        f"Highest run scorer for {TEAM_RCB}": "R.Patidar",
        f"Highest wicket taker for {TEAM_RCB}": "K.Pandya",
        f"Economical bowler for {TEAM_RCB}": "B.Kumar",
        f"How many extras will {TEAM_RCB} give": "6-10",
        f"50's for {TEAM_RCB}": "2",
        f"100 for {TEAM_RCB}": "0",
        f"Projected score for {TEAM_RCB}": "176-200",
        "Which team will hit more sixes": TEAM_SRH,
        "Who will win": TEAM_RCB,
    }


def main():
    app = app_module.app
    with app.app_context():
        match = (
            Match.query.filter(Match.team_a.in_([TEAM_RCB, TEAM_SRH]))
            .filter(Match.team_b.in_([TEAM_RCB, TEAM_SRH]))
            .order_by(Match.start_time.asc())
            .first()
        )
        if not match:
            raise SystemExit("RCB vs SRH match not found")

        answers = build_answer_key(match.team_a, match.team_b)
        polls = Poll.query.filter_by(match_id=match.id).all()
        applied = 0
        skipped = []

        for poll in polls:
            correct = answers.get(poll.question)
            if not correct:
                skipped.append(poll.question)
                continue
            result = Result.query.filter_by(poll_id=poll.id).first()
            if result:
                result.correct_option = correct
            else:
                db.session.add(Result(match_id=match.id, poll_id=poll.id, correct_option=correct))

            for vote in Vote.query.filter_by(poll_id=poll.id).all():
                vote.points = 1 if vote.option == correct else 0

            applied += 1

        match.status = "completed"
        update_match_standings(match.id)
        db.session.commit()

        print(f"Applied results for {applied} polls on {match.display_name}")
        if skipped:
            print("Skipped questions:")
            for question in skipped:
                print(f"- {question}")


if __name__ == "__main__":
    main()
