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
from services.polls import build_daily_polls


def main():
    app = app_module.app
    with app.app_context():
        target_match = (
            Match.query.filter(Match.team_a.in_(["Royal Challengers Bengaluru", "Sunrisers Hyderabad"]))
            .filter(Match.team_b.in_(["Royal Challengers Bengaluru", "Sunrisers Hyderabad"]))
            .order_by(Match.start_time.asc())
            .first()
        )

        if not target_match:
            raise SystemExit("No RCB vs SRH match found")

        new_polls = build_daily_polls(target_match)
        if not new_polls:
            raise SystemExit("Daily polls not defined for this matchup")

        Poll.query.filter_by(match_id=target_match.id).delete()
        db.session.flush()
        db.session.add_all(new_polls)
        db.session.commit()

        print(f"Applied daily polls to match {target_match.display_name} ({target_match.start_time})")


if __name__ == "__main__":
    main()
