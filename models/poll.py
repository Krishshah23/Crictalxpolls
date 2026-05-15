from datetime import datetime
from . import db


class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    question = db.Column(db.String(200), nullable=False)
    options = db.Column(db.JSON, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_locked = db.Column(db.Boolean, default=False, nullable=False)
    is_toss_poll = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    match = db.relationship("Match", back_populates="polls")
    votes = db.relationship("Vote", back_populates="poll", cascade="all, delete-orphan")
