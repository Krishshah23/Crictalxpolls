from datetime import datetime
from . import db


class MatchStanding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    match_points = db.Column(db.Integer, default=0, nullable=False)
    winner_points = db.Column(db.Integer, default=0, nullable=False)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    match = db.relationship("Match")
    user = db.relationship("User")

    __table_args__ = (
        db.UniqueConstraint("match_id", "user_id", name="uq_match_standing_match_user"),
    )
