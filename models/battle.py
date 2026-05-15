from datetime import datetime
from . import db


class Battle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    challenger_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    opponent_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    status = db.Column(db.String(32), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    accepted_at = db.Column(db.DateTime, nullable=True)

    challenger = db.relationship("User", foreign_keys=[challenger_id])
    opponent = db.relationship("User", foreign_keys=[opponent_id])
    match = db.relationship("Match")
