from datetime import datetime, timedelta
from models import db
from models.match import Match
from models.poll import Poll
from models.result import Result
from models.vote import Vote
from services.standings import update_match_standings
from services.boosts import apply_boost


def run_points_calculation(match_id=None):
    matches = Match.query.all() if match_id is None else [Match.query.get(match_id)]
    for match in matches:
        if not match:
            continue

        for poll in Poll.query.filter_by(match_id=match.id).all():
            result = Result.query.filter_by(poll_id=poll.id).first()
            if not result or not result.correct_option:
                for vote in Vote.query.filter_by(poll_id=poll.id).all():
                    vote.points = 0
                continue

            for vote in Vote.query.filter_by(poll_id=poll.id).all():
                if vote.option == result.correct_option:
                    vote.points = 2 * max(vote.confidence, 1)
                else:
                    vote.points = -(max(vote.confidence, 1) - 1)
                apply_boost(vote)

        update_match_standings(match.id)

    db.session.commit()


def lock_due_polls() -> None:
    now = datetime.utcnow()
    updated = False
    for poll in Poll.query.filter_by(is_locked=False, is_active=True).all():
        match = poll.match
        if not match:
            continue
        lock_time = match.start_time - timedelta(minutes=30) if poll.is_toss_poll else match.start_time
        if now >= lock_time:
            poll.is_locked = True
            updated = True
    if updated:
        db.session.commit()


def update_match_statuses() -> None:
    now = datetime.utcnow()
    matches = Match.query.all()
    updated = False

    for match in matches:
        if match.status == "completed":
            continue

        end_time = match.end_time or (match.start_time + timedelta(hours=4))
        if now >= end_time:
            match.status = "completed"
            updated = True
        elif now >= match.start_time:
            if match.status != "live":
                match.status = "live"
                updated = True
        else:
            if match.status != "upcoming":
                match.status = "upcoming"
                updated = True

    if updated:
        db.session.commit()
