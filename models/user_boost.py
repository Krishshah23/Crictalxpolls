from datetime import datetime
from . import db


class UserBoost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    boost_type = db.Column(db.String(20), default="2x", nullable=False)
    multiplier = db.Column(db.Integer, default=2, nullable=False)
    status = db.Column(db.String(20), default="active", nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    applied_vote_id = db.Column(db.Integer, db.ForeignKey("vote.id"), nullable=True)
    applied_vote_ids = db.Column(db.JSON, default=list, nullable=False)  # Store list of vote IDs for multi-vote boost
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    used_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    applied_vote = db.relationship("Vote")
