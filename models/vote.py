from datetime import datetime
from . import db


class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    option = db.Column(db.String(200), nullable=False)
    confidence = db.Column(db.Integer, default=1, nullable=False)
    points = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User", back_populates="votes")
    poll = db.relationship("Poll", back_populates="votes")
