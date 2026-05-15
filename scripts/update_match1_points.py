import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models import db
from models.match import Match
from models.poll import Poll
from models.result import Result
from models.user import User
from models.vote import Vote
from services.scheduler import run_points_calculation
from services.standings import update_match_standings


TEAM_RCB = "Royal Challengers Bengaluru"
TEAM_SRH = "Sunrisers Hyderabad"


def _find_match() -> Match | None:
    return (
        Match.query.filter(Match.team_a.in_([TEAM_RCB, TEAM_SRH]))
        .filter(Match.team_b.in_([TEAM_RCB, TEAM_SRH]))
        .order_by(Match.start_time.asc())
        .first()
    )


def main() -> None:
    app = app_module.app
    with app.app_context():
        match = _find_match()
        if not match:
            raise SystemExit("RCB vs SRH match not found")

        match.status = "completed"
        polls = Poll.query.filter_by(match_id=match.id).all()
        targets = {"Krish": 9, "Tirth": 8, "Nithin": 7}
        users = {
            user.username: user
            for user in User.query.filter(User.username.in_(list(targets.keys()))).all()
        }

        poll_ids = [poll.id for poll in polls]
        for user in users.values():
            Vote.query.filter(Vote.user_id == user.id, Vote.poll_id.in_(poll_ids)).delete(
                synchronize_session=False
            )

        for poll in polls:
            if not poll.options:
                continue
            correct = poll.options[0]
            result = Result.query.filter_by(poll_id=poll.id).first()
            if result:
                result.correct_option = correct
            else:
                db.session.add(
                    Result(match_id=match.id, poll_id=poll.id, correct_option=correct)
                )

            incorrect = poll.options[1] if len(poll.options) > 1 else None

            for name in list(targets.keys()):
                user = users.get(name)
                if not user:
                    continue

                if targets[name] > 0:
                    db.session.add(Vote(user_id=user.id, poll_id=poll.id, option=correct))
                    targets[name] -= 1
                elif incorrect and incorrect != correct:
                    db.session.add(Vote(user_id=user.id, poll_id=poll.id, option=incorrect))

        run_points_calculation(match.id)
        update_match_standings(match.id)
        db.session.commit()

        print("Applied targets. Remaining:", targets)


if __name__ == "__main__":
    main()
