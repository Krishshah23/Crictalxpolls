import os
import json
import threading
import time
from datetime import datetime, timedelta
from flask import Flask
from flask_login import current_user
from dotenv import load_dotenv
from sqlalchemy import text
from config import Config
from models import db, login_manager, migrate
from models.user import User
from models.match import Match
from models.player import Player
from models.match_standing import MatchStanding
from models.poll import Poll
from models.user_boost import UserBoost
from models.roulette_spin import RouletteSpin
from models.battle import Battle
from services.polls import build_standard_polls
from services.scheduler import lock_due_polls
from routes.auth import auth_bp
from routes.main import main_bp
from routes.polls import polls_bp
from routes.admin import admin_bp
from routes.api import api_bp


def create_app():
    load_dotenv()

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)

    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(polls_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_score_ticker():
        if not current_user or not current_user.is_authenticated:
            return {}

        matches = (
            Match.query.filter(Match.status == "completed")
            .order_by(Match.start_time.desc())
            .limit(8)
            .all()
        )
        items = []
        for match in matches:
            winner = (
                MatchStanding.query.filter_by(match_id=match.id, winner_points=1)
                .join(User, User.id == MatchStanding.user_id)
                .order_by(MatchStanding.match_points.desc(), User.username.asc())
                .first()
            )
            winner_name = winner.user.username if winner else "TBD"
            items.append(f"{match.display_name} · {winner_name} leads")

        return {"score_ticker_items": items}

    with app.app_context():
        db.create_all()
        _ensure_schema()
        _ensure_poll_flags()
        _bootstrap_seed_snapshot(app)
        if os.environ.get("BOOTSTRAP_DB_ON_STARTUP", "true").lower() == "true":
            seed_data(app)

    if (
        os.environ.get("ENABLE_POLL_WORKER", "true").lower() == "true"
        and os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    ):
        thread = threading.Thread(target=_poll_lock_worker, args=(app,), daemon=True)
        thread.start()

    return app


def _poll_lock_worker(app: Flask) -> None:
    while True:
        with app.app_context():
            lock_due_polls()
        time.sleep(60)


def _ensure_schema() -> None:
    def _has_column(table: str, column: str) -> bool:
        rows = db.session.execute(text(f"PRAGMA table_info({table})")).fetchall()
        return any(row[1] == column for row in rows)

    if not _has_column("poll", "is_locked"):
        db.session.execute(text("ALTER TABLE poll ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT 0"))
    if not _has_column("poll", "is_toss_poll"):
        db.session.execute(text("ALTER TABLE poll ADD COLUMN is_toss_poll BOOLEAN NOT NULL DEFAULT 0"))
    if not _has_column("vote", "confidence"):
        db.session.execute(text("ALTER TABLE vote ADD COLUMN confidence INTEGER NOT NULL DEFAULT 1"))
    db.session.commit()


def _ensure_poll_flags() -> None:
    polls = Poll.query.filter(Poll.is_toss_poll.is_(False)).all()
    updated = False
    for poll in polls:
        if "toss" in poll.question.lower():
            poll.is_toss_poll = True
            updated = True
    if updated:
        db.session.commit()


def _bootstrap_seed_snapshot(app: Flask) -> None:
    snapshot_path = os.path.join(app.root_path, "services", "seed_snapshot.json")
    if not os.path.exists(snapshot_path):
        return

    if User.query.count() > 0:
        return

    with open(snapshot_path, "r", encoding="utf-8") as handle:
        snapshot = json.load(handle)

    table_order = [
        "user",
        "match",
        "player",
        "poll",
        "result",
        "user_boost",
        "roulette_spin",
        "battle",
        "match_standing",
        "vote",
        "admin_audit_log",
    ]

    for table_name in table_order:
        rows = snapshot.get(table_name, [])
        if not rows:
            continue

        table = db.metadata.tables.get(table_name)
        if table is None:
            continue

        prepared_rows = []
        for row in rows:
            prepared = {}
            for column in table.columns:
                value = row.get(column.name)
                if value is None:
                    prepared[column.name] = None
                    continue
                if hasattr(column.type, "python_type"):
                    try:
                        py_type = column.type.python_type
                    except NotImplementedError:
                        py_type = None
                else:
                    py_type = None

                if py_type is bool:
                    prepared[column.name] = bool(value)
                elif py_type is int:
                    prepared[column.name] = int(value)
                elif py_type is float:
                    prepared[column.name] = float(value)
                elif py_type is datetime:
                    prepared[column.name] = datetime.fromisoformat(value)
                elif column.name == "applied_vote_ids" and isinstance(value, str):
                    prepared[column.name] = json.loads(value)
                else:
                    prepared[column.name] = value
            prepared_rows.append(prepared)

        db.session.execute(table.insert(), prepared_rows)

    db.session.commit()


def seed_data(app: Flask) -> None:
    if User.query.count() == 0:
        admin = User(
            username=app.config["ADMIN_USERNAME"],
            is_admin=True
        )
        admin.set_password(app.config["ADMIN_PASSWORD"])
        db.session.add(admin)

        for username in ["Krish", "Nithin", "Tirth"]:
            user = User(username=username)
            user.set_password("crictalx123")
            db.session.add(user)

    if Player.query.count() == 0:
        squads_path = os.path.join(app.root_path, "services", "squads_2026.json")
        if os.path.exists(squads_path):
            import json

            with open(squads_path, "r", encoding="utf-8") as handle:
                squads = json.load(handle)

            players = []
            for team, roster in squads.get("teams", {}).items():
                for player in roster:
                    name = player.get("name")
                    role = player.get("role")
                    if not name or not role:
                        continue
                    players.append(Player(name=name, team=team, role=role))

            if players:
                db.session.add_all(players)

    if Match.query.count() == 0:
        fixtures_path = os.path.join(app.root_path, "services", "fixtures_2026.json")
        if os.path.exists(fixtures_path):
            import json

            with open(fixtures_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)

            fixtures = payload.get("fixtures", [])
            for fixture in fixtures:
                start_time = datetime.fromisoformat(fixture["start_time"])
                end_time = start_time + timedelta(hours=4)
                match = Match(
                    team_a=fixture["team_a"],
                    team_b=fixture["team_b"],
                    start_time=start_time,
                    end_time=end_time,
                    status="upcoming",
                )
                db.session.add(match)
                db.session.flush()
                db.session.add_all(build_standard_polls(match))
        else:
            start_time = datetime.utcnow() + timedelta(hours=6)
            end_time = start_time + timedelta(hours=4)
            match = Match(
                team_a="Mumbai Indians",
                team_b="Chennai Super Kings",
                start_time=start_time,
                end_time=end_time,
                status="upcoming"
            )
            db.session.add(match)
            db.session.flush()

            db.session.add_all(build_standard_polls(match))

    db.session.commit()


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "0") == "1")
