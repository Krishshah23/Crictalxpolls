from datetime import datetime, timedelta
import csv
import io
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import case, func
from models import db
from models.match import Match
from models.poll import Poll
from models.vote import Vote
from models.result import Result
from models.user import User
from models.player import Player
from models.audit_log import AdminAuditLog
from services.ipl_data import TEAMS, ROLES, ROLE_GROUPS
from services.scheduler import run_points_calculation
from services.polls import build_standard_polls
from services.standings import update_match_standings
from services.boosts import apply_boost


admin_bp = Blueprint("admin", __name__)


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        return False
    return True


@admin_bp.before_request
def guard_admin():
    if request.endpoint == "admin.admin_dashboard" or request.endpoint.startswith("admin."):
        if not admin_required():
            flash("Admin access required.", "error")
            return redirect(url_for("main.dashboard"))


def _log_admin_action(action: str, entity: str, detail: str | None = None) -> None:
    if not current_user.is_authenticated:
        return
    log = AdminAuditLog(
        admin_id=current_user.id,
        action=action,
        entity=entity,
        detail=detail,
        ip_address=request.headers.get("X-Forwarded-For", request.remote_addr),
    )
    db.session.add(log)


@admin_bp.route("/admin")
@login_required
def admin_dashboard():
    matches = Match.query.order_by(Match.start_time.desc()).all()
    users = User.query.order_by(User.created_at.desc()).all()
    players = Player.query.order_by(Player.team.asc(), Player.name.asc()).all()
    poll_count = Poll.query.count()
    user_count = len(users)
    match_count = len(matches)
    rosters = {team: {role: [] for role in ROLES} for team in TEAMS}
    for player in players:
        if player.team not in rosters:
            rosters[player.team] = {role: [] for role in ROLES}
        role_bucket = player.role if player.role in ROLES else "Batsman"
        rosters[player.team][role_bucket].append(player)

    audit_logs = (
        AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc())
        .limit(30)
        .all()
    )

    week_cutoff = datetime.utcnow() - timedelta(days=7)
    admin_rows = (
        db.session.query(
            User.username,
            func.count(AdminAuditLog.id).label("total"),
            func.sum(case((AdminAuditLog.created_at >= week_cutoff, 1), else_=0)).label("last_week"),
        )
        .join(AdminAuditLog, AdminAuditLog.admin_id == User.id)
        .group_by(User.username)
        .order_by(func.count(AdminAuditLog.id).desc())
        .all()
    )

    admin_activity = []
    for row in admin_rows:
        admin_activity.append({
            "username": row.username,
            "total": int(row.total or 0),
            "last_week": int(row.last_week or 0),
        })

    action_rows = (
        db.session.query(
            AdminAuditLog.action,
            func.count(AdminAuditLog.id).label("total"),
        )
        .group_by(AdminAuditLog.action)
        .order_by(func.count(AdminAuditLog.id).desc())
        .all()
    )
    action_breakdown = [
        {"action": row.action, "total": int(row.total or 0)}
        for row in action_rows
    ]

    return render_template(
        "admin.html",
        matches=matches,
        users=users,
        players=players,
        rosters=rosters,
        teams=TEAMS,
        roles=ROLES,
        user_count=user_count,
        match_count=match_count,
        poll_count=poll_count,
        audit_logs=audit_logs,
        admin_activity=admin_activity,
        action_breakdown=action_breakdown,
    )


@admin_bp.route("/admin/results")
@login_required
def admin_results():
    matches = Match.query.all()
    status_order = {"live": 0, "completed": 1, "upcoming": 2}

    def _sort_key(match: Match):
        priority = status_order.get(match.status, 3)
        if match.status == "upcoming":
            return (priority, match.start_time)
        return (priority, -match.start_time.timestamp())

    matches = sorted(matches, key=_sort_key)

    results_map = {}
    for match in matches:
        for poll in match.polls:
            result = Result.query.filter_by(poll_id=poll.id).first()
            if result and result.correct_option:
                results_map[poll.id] = result.correct_option

    return render_template("admin_results.html", matches=matches, results_map=results_map)


@admin_bp.route("/admin/results/save", methods=["POST"])
@login_required
def save_results():
    match_id = request.form.get("match_id", type=int)
    if not match_id:
        flash("Match not found.", "error")
        return redirect(url_for("admin.admin_results"))

    match = Match.query.get_or_404(match_id)
    save_single = request.form.get("save_single")

    polls = match.polls
    poll_map = {poll.id: poll for poll in polls}

    poll_ids_to_update = []
    if save_single:
        try:
            poll_ids_to_update = [int(save_single)]
        except ValueError:
            poll_ids_to_update = []
    else:
        poll_ids_to_update = [poll.id for poll in polls]

    updated = 0
    for poll_id in poll_ids_to_update:
        poll = poll_map.get(poll_id)
        if not poll:
            continue
        key = f"correct_option_{poll.id}"
        correct_option = request.form.get(key, "").strip()
        if not correct_option:
            continue

        result = Result.query.filter_by(poll_id=poll.id).first()
        if result:
            result.correct_option = correct_option
        else:
            db.session.add(Result(match_id=match.id, poll_id=poll.id, correct_option=correct_option))

        for vote in Vote.query.filter_by(poll_id=poll.id).all():
            if vote.option == correct_option:
                vote.points = 2 * max(vote.confidence, 1)
            else:
                vote.points = -(max(vote.confidence, 1) - 1)
            apply_boost(vote)
        updated += 1

    remaining = (
        db.session.query(Poll.id)
        .filter(Poll.match_id == match.id)
        .outerjoin(Result, Result.poll_id == Poll.id)
        .filter((Result.correct_option.is_(None)) | (Result.id.is_(None)))
        .count()
    )
    if remaining == 0:
        match.status = "completed"

    update_match_standings(match.id)
    db.session.commit()

    if updated:
        flash("Results saved.", "success")
    else:
        flash("No changes to save.", "error")
    _log_admin_action("update", "results", f"Match {match.display_name} updated")
    db.session.commit()
    return redirect(url_for("admin.admin_results"))


@admin_bp.route("/admin/match", methods=["POST"])
@login_required
def add_match():
    team_a = request.form.get("team_a", "").strip()
    team_b = request.form.get("team_b", "").strip()
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")

    if not team_a or not team_b or not start_time:
        flash("Team names and start time are required.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    if team_a == team_b:
        flash("Team A and Team B must be different.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    match = Match(
        team_a=team_a,
        team_b=team_b,
        start_time=datetime.fromisoformat(start_time),
        end_time=datetime.fromisoformat(end_time) if end_time else None,
        status="upcoming"
    )
    db.session.add(match)
    db.session.flush()
    db.session.add_all(build_standard_polls(match))
    db.session.commit()

    _log_admin_action("create", "match", match.display_name)
    db.session.commit()
    flash("Match added.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/match/<int:match_id>/delete", methods=["POST"])
@login_required
def delete_match(match_id):
    match = Match.query.get_or_404(match_id)
    match_name = match.display_name
    db.session.delete(match)
    db.session.commit()
    _log_admin_action("delete", "match", match_name)
    db.session.commit()
    flash("Match deleted.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/poll", methods=["POST"])
@login_required
def add_poll():
    match_id = int(request.form.get("match_id"))
    question = request.form.get("question", "").strip()
    options_raw = request.form.get("options", "")
    option_source = request.form.get("option_source", "custom")
    options = [item.strip() for item in options_raw.split(",") if item.strip()]

    if not question or not options:
        if option_source == "custom":
            flash("Question and options required.", "error")
            return redirect(url_for("admin.admin_dashboard"))

    match = Match.query.get_or_404(match_id)
    options = _resolve_poll_options(match, option_source, options)
    if not options:
        flash("No options found for that source. Add players first.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    poll = Poll(match_id=match_id, question=question, options=options)
    db.session.add(poll)
    db.session.commit()
    _log_admin_action("create", "poll", f"{match.display_name}: {question}")
    db.session.commit()
    flash("Custom poll added.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/player", methods=["POST"])
@login_required
def add_player():
    name = request.form.get("name", "").strip()
    team = request.form.get("team", "").strip()
    role = request.form.get("role", "").strip() or "Batsman"

    if not name or not team:
        flash("Player name and team are required.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    player = Player(name=name, team=team, role=role)
    db.session.add(player)
    db.session.commit()
    _log_admin_action("create", "player", f"{player.name} ({player.team})")
    db.session.commit()
    flash("Player added.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/user/<int:user_id>/delete", methods=["POST"])
@login_required
def delete_user(user_id):
    if current_user.id == user_id:
        flash("You cannot delete your own account.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    user = User.query.get_or_404(user_id)
    username = user.username
    db.session.delete(user)
    db.session.commit()
    _log_admin_action("delete", "user", username)
    db.session.commit()
    flash("User removed.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/poll/<int:poll_id>/result", methods=["POST"])
@login_required
def set_poll_result(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    correct_option = request.form.get("correct_option", "").strip()
    if not correct_option:
        flash("Select a correct option.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    result = Result.query.filter_by(poll_id=poll.id).first()
    if result:
        result.correct_option = correct_option
    else:
        db.session.add(Result(match_id=poll.match_id, poll_id=poll.id, correct_option=correct_option))

    for vote in Vote.query.filter_by(poll_id=poll.id).all():
        if vote.option == correct_option:
            vote.points = 2 * max(vote.confidence, 1)
        else:
            vote.points = -(max(vote.confidence, 1) - 1)
        apply_boost(vote)

    # Mark match completed once all polls have results
    remaining = (
        db.session.query(Poll.id)
        .filter(Poll.match_id == poll.match_id)
        .outerjoin(Result, Result.poll_id == Poll.id)
        .filter((Result.correct_option.is_(None)) | (Result.id.is_(None)))
        .count()
    )
    if remaining == 0:
        poll.match.status = "completed"

    update_match_standings(poll.match_id)

    db.session.commit()
    _log_admin_action("update", "result", f"{poll.match.display_name}: {poll.question}")
    db.session.commit()
    flash("Result saved and points updated.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/run-points", methods=["POST"])
@login_required
def run_points():
    run_points_calculation()
    _log_admin_action("run", "points", "Manual recalculation")
    db.session.commit()
    flash("Points calculation triggered.", "success")
    return redirect(url_for("admin.admin_dashboard"))


@admin_bp.route("/admin/poll/<int:poll_id>/lock", methods=["POST"])
@login_required
def lock_poll(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    poll.is_locked = True
    db.session.commit()
    _log_admin_action("lock", "poll", f"{poll.match.display_name}: {poll.question}")
    db.session.commit()
    flash("Poll locked.", "success")
    return redirect(url_for("admin.admin_results"))


@admin_bp.route("/admin/export/votes")
@login_required
def export_votes():
    votes = (
        Vote.query.join(Poll, Poll.id == Vote.poll_id)
        .join(Match, Match.id == Poll.match_id)
        .join(User, User.id == Vote.user_id)
        .order_by(Match.start_time.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "username",
        "match",
        "start_time_ist",
        "question",
        "option",
        "confidence",
        "points",
        "result",
        "status",
    ])

    for vote in votes:
        match = vote.poll.match
        if vote.points > 0:
            result = "correct"
        elif vote.points < 0:
            result = "incorrect"
        else:
            result = "pending"
        writer.writerow([
            vote.user.username,
            match.display_name,
            match.start_time_ist.strftime("%Y-%m-%d %H:%M IST"),
            vote.poll.question,
            vote.option,
            vote.confidence,
            vote.points,
            result,
            match.status,
        ])

    _log_admin_action("export", "votes", f"{len(votes)} rows")
    db.session.commit()

    filename = f"crictalx_votes_all_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    response = current_app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


def _resolve_poll_options(match: Match, option_source: str, custom_options: list[str]) -> list[str]:
    if option_source == "custom":
        return custom_options

    if option_source == "team_a_all":
        return _players_for_team(match.team_a)
    if option_source == "team_b_all":
        return _players_for_team(match.team_b)
    if option_source == "both_teams_all":
        return _players_for_team(match.team_a) + _players_for_team(match.team_b)

    if option_source == "team_a_batsmen":
        return _players_for_team(match.team_a, ROLE_GROUPS["batsmen"])
    if option_source == "team_b_batsmen":
        return _players_for_team(match.team_b, ROLE_GROUPS["batsmen"])
    if option_source == "team_a_all_rounders":
        return _players_for_team(match.team_a, ROLE_GROUPS["all_rounders"])
    if option_source == "team_b_all_rounders":
        return _players_for_team(match.team_b, ROLE_GROUPS["all_rounders"])
    if option_source == "team_a_bowlers":
        return _players_for_team(match.team_a, ROLE_GROUPS["bowlers"])
    if option_source == "team_b_bowlers":
        return _players_for_team(match.team_b, ROLE_GROUPS["bowlers"])

    return custom_options


def _players_for_team(team: str, roles: list[str] | None = None) -> list[str]:
    query = Player.query.filter_by(team=team)
    if roles:
        query = query.filter(Player.role.in_(roles))
    return [player.name for player in query.order_by(Player.name.asc()).all()]