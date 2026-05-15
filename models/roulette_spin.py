from datetime import datetime
from . import db


class RouletteSpin(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    reward = db.Column(db.String(120), nullable=False)
    boost_type = db.Column(db.String(20), default="2x", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship("User")
