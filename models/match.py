from datetime import datetime, timedelta, timezone
from . import db


class Match(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    api_id = db.Column(db.String(64), nullable=True)
    team_a = db.Column(db.String(80), nullable=False)
    team_b = db.Column(db.String(80), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(32), default="upcoming", nullable=False)

    polls = db.relationship("Poll", back_populates="match", cascade="all, delete-orphan")

    @property
    def display_name(self) -> str:
        return f"{self.team_a} vs {self.team_b}"

    @property
    def has_started(self) -> bool:
        return datetime.utcnow() >= self.start_time

    @property
    def start_time_ist(self) -> datetime:
        ist = timezone(timedelta(hours=5, minutes=30))
        return self.start_time.replace(tzinfo=timezone.utc).astimezone(ist)

    @property
    def start_time_ist_timestamp(self) -> int:
        return int(self.start_time_ist.timestamp())
