from models import db
from models.match import Match
from models.match_standing import MatchStanding
from models.poll import Poll
from models.user import User
from models.vote import Vote


def compute_user_streaks(user_ids: list[int]) -> dict[int, dict[str, int]]:
    if not user_ids:
        return {}

    rows = (
        db.session.query(
            MatchStanding.user_id,
            MatchStanding.match_points,
            Match.start_time,
        )
        .join(Match, Match.id == MatchStanding.match_id)
        .filter(MatchStanding.user_id.in_(user_ids))
        .order_by(Match.start_time.asc())
        .all()
    )

    streaks = {user_id: {"current": 0, "best": 0} for user_id in user_ids}
    for row in rows:
        record = streaks.get(row.user_id)
        if record is None:
            continue
        if row.match_points > 0:
            record["current"] += 1
        else:
            record["current"] = 0
        if record["current"] > record["best"]:
            record["best"] = record["current"]

    return streaks


def update_match_standings(match_id: int) -> None:
    match = Match.query.get(match_id)
    if not match:
        return

    polls = Poll.query.filter_by(match_id=match.id).all()
    poll_ids = [poll.id for poll in polls]
    users = User.query.filter_by(is_admin=False).all()

    user_points = {}
    for user in users:
        match_points = 0
        if poll_ids:
            match_points = (
                db.session.query(db.func.coalesce(db.func.sum(Vote.points), 0))
                .filter(Vote.user_id == user.id, Vote.poll_id.in_(poll_ids))
                .scalar()
                or 0
            )
        user_points[user.id] = int(match_points)

    max_points = max(user_points.values(), default=0)

    for user in users:
        match_points = user_points.get(user.id, 0)
        winner_points = 1 if max_points and match_points == max_points else 0

        standing = MatchStanding.query.filter_by(match_id=match.id, user_id=user.id).first()
        if standing:
            standing.match_points = match_points
            standing.winner_points = winner_points
        else:
            db.session.add(
                MatchStanding(
                    match_id=match.id,
                    user_id=user.id,
                    match_points=match_points,
                    winner_points=winner_points,
                )
            )

    db.session.commit()


def update_all_match_standings() -> None:
    matches = Match.query.all()
    for match in matches:
        update_match_standings(match.id)
