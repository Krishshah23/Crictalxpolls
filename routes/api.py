from flask import Blueprint, jsonify
from flask_login import login_required
from models.poll import Poll
from models.vote import Vote


api_bp = Blueprint("api", __name__)


@api_bp.route("/api/match/<int:match_id>/polls")
@login_required
def match_polls(match_id):
    polls = Poll.query.filter_by(match_id=match_id).all()
    payload = []
    for poll in polls:
        votes = Vote.query.filter_by(poll_id=poll.id).all()
        counts = {}
        for option in poll.options:
            counts[option] = len([v for v in votes if v.option == option])
        payload.append({
            "poll_id": poll.id,
            "question": poll.question,
            "counts": counts,
            "total": len(votes)
        })

    return jsonify({"polls": payload})