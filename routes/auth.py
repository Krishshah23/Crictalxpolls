from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from sqlalchemy import func, desc
from models import db
from models.match import Match
from models.poll import Poll
from models.user import User
from models.vote import Vote


auth_bp = Blueprint("auth", __name__)


def _get_auth_stats() -> dict:
    players = User.query.filter_by(is_admin=False).count()
    total_votes = Vote.query.count()
    polls_open = Poll.query.filter_by(is_active=True, is_locked=False).count()

    next_match = (
        Match.query.filter_by(status="upcoming")
        .order_by(Match.start_time.asc())
        .first()
    )
    next_match_label = next_match.display_name if next_match else "TBD"

    leader = (
        db.session.query(
            User.username,
            func.coalesce(func.sum(Vote.points), 0).label("points"),
        )
        .outerjoin(Vote, Vote.user_id == User.id)
        .filter(User.is_admin == False)
        .group_by(User.id)
        .order_by(desc("points"))
        .first()
    )
    leading_name = leader.username if leader else "TBD"
    top_score = int(leader.points) if leader else 0

    return {
        "players": players,
        "total_votes": total_votes,
        "top_score": top_score,
        "leading": leading_name,
        "next_match": next_match_label,
        "polls_open": polls_open,
    }


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("main.dashboard"))

        flash("Invalid username or password", "error")

    return render_template("login.html", auth_stats=_get_auth_stats())


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("auth.signup"))

        if User.query.filter_by(username=username).first():
            flash("Username already exists.", "error")
            return redirect(url_for("auth.signup"))

        user = User(username=username)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        login_user(user, remember=True)
        return redirect(url_for("main.dashboard"))

    return render_template("signup.html", auth_stats=_get_auth_stats())


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))