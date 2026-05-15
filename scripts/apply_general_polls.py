import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.append(ROOT)

import app as app_module
from models import db
from models.match import Match
from models.poll import Poll
from models.vote import Vote
from services.polls import build_standard_polls


def main():
    app = app_module.app
    with app.app_context():
        matches = Match.query.order_by(Match.start_time.asc()).all()
        if not matches:
            raise SystemExit("No matches found")

        for match in matches:
            poll_ids = [poll.id for poll in Poll.query.filter_by(match_id=match.id).all()]
            if poll_ids:
                Vote.query.filter(Vote.poll_id.in_(poll_ids)).delete(synchronize_session=False)
            Poll.query.filter_by(match_id=match.id).delete()
            db.session.flush()
            db.session.add_all(build_standard_polls(match))

        db.session.commit()
        print(f"Applied daily questions to {len(matches)} matches")


if __name__ == "__main__":
    main()
