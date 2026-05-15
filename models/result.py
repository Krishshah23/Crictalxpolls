from datetime import datetime
from . import db


class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("match.id"), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey("poll.id"), nullable=False)
    correct_option = db.Column(db.String(200), nullable=True)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
