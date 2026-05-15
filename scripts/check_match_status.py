import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models.match import Match
from models.poll import Poll
from models.result import Result
from models.match_standing import MatchStanding
from models.user import User
from models.vote import Vote


def main() -> None:
    app = app_module.app
    with app.app_context():
        match = Match.query.filter(
            Match.team_a == "Mumbai Indians",
            Match.team_b == "Kolkata Knight Riders",
        ).first()

        if not match:
            print("Match not found")
            return

        polls = Poll.query.filter_by(match_id=match.id).all()
        poll_ids = [poll.id for poll in polls]
        results = Result.query.filter(Result.poll_id.in_(poll_ids)).all() if poll_ids else []
        standings = MatchStanding.query.filter_by(match_id=match.id).all()
        result_map = {result.poll_id: result for result in results}

        print(f"Match: {match.id} {match.display_name} status={match.status}")
        print(f"Polls: {len(polls)}")
        print(f"Results with correct: {len([r for r in results if r.correct_option])}")
        print(f"Standings rows: {len(standings)}")

        missing = [poll.question for poll in polls if not result_map.get(poll.id) or not result_map[poll.id].correct_option]
        if missing:
            print("Missing results:")
            for question in missing:
                print(f"- {question}")

        for user in User.query.filter_by(is_admin=False).all():
            points = 0
            if poll_ids:
                points = sum(
                    vote.points
                    for vote in Vote.query.filter(
                        Vote.user_id == user.id, Vote.poll_id.in_(poll_ids)
                    ).all()
                )
            print(f"{user.username}: match_points={points}")


if __name__ == "__main__":
    main()
