from datetime import datetime, timedelta
import csv
import io
import os
import random
from urllib.parse import unquote
from uuid import uuid4
from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from sqlalchemy import case, func, or_
from models.match import Match
from models import db
from models.vote import Vote
from models.poll import Poll
from models.user import User
from models.match_standing import MatchStanding
from models.user_boost import UserBoost
from models.roulette_spin import RouletteSpin
from models.battle import Battle
from models.player import Player
from services.standings import update_match_standings, compute_user_streaks
from services.scheduler import update_match_statuses
from services.ipl_data import TEAMS, ROLES


main_bp = Blueprint("main", __name__)


def _build_trophies(total_votes: int, total_points: int, hit_rate: int, matches_played: int, avg_points: float, high_confidence_picks: int, accuracy: int) -> list[str]:
    trophies = []
    if total_votes >= 5:
        trophies.append("First Five")
    if hit_rate >= 50 and total_votes >= 5:
        trophies.append("Accuracy Ace")
    if accuracy >= 65 and total_votes >= 10:
        trophies.append("Sharpshooter")
    if total_points >= 50:
        trophies.append("Point Breaker")
    if matches_played >= 3:
        trophies.append("Matchday Regular")
    if avg_points >= 12 and matches_played >= 4:
        trophies.append("Consistent Climber")
    if high_confidence_picks >= 5:
        trophies.append("High Roller")
    if not trophies:
        trophies = ["Rising Star"]
    return trophies


def _build_fun_badges(current_streak: int, best_streak: int, accuracy: int, avg_confidence: float, high_confidence_picks: int, total_points: int) -> list[dict]:
    badges = []
    if current_streak >= 3:
        badges.append({"label": "Hot Streak", "hint": f"{current_streak} straight wins are live."})
    if best_streak >= 5:
        badges.append({"label": "Clutch Run", "hint": f"Best streak: {best_streak}. You can close games."})
    if accuracy >= 60:
        badges.append({"label": "Sharp Eye", "hint": f"{accuracy}% accuracy keeps you ahead of the pack."})
    if avg_confidence >= 2.0:
        badges.append({"label": "Risk Rider", "hint": f"Average confidence {avg_confidence}× means you play bold."})
    if high_confidence_picks >= 20:
        badges.append({"label": "Big Swinger", "hint": f"{high_confidence_picks} high-risk picks so far."})
    if total_points >= 100:
        badges.append({"label": "Point Forge", "hint": f"{total_points} total points on the board."})
    if accuracy >= 75:
        badges.append({"label": "Sniper", "hint": f"Elite accuracy at {accuracy}% means your picks are surgical."})
    if current_streak == 0 and best_streak >= 8:
        badges.append({"label": "Comeback Core", "hint": "You’ve rebuilt from cold stretches before."})
    if not badges:
        badges = [{"label": "Fresh Start", "hint": "Your badge set will grow as the season builds."}]
    return badges


def _roulette_options() -> list[dict]:
    return [
        {"label": "2× Surge", "type": "2x", "multiplier": 2, "weight": 16, "tone": "gold", "hint": "Solid reliability. Your go-to boost."},
        {"label": "3× Thunder", "type": "3x", "multiplier": 3, "weight": 16, "tone": "fire", "hint": "Bold and wild. When you trust your pick."},
        {"label": "4× Turbo", "type": "4x", "multiplier": 4, "weight": 11, "tone": "acid", "hint": "High voltage. Game-changer energy."},
        {"label": "5× Jackpot", "type": "5x", "multiplier": 5, "weight": 7, "tone": "ice", "hint": "Rare. Loud. Season-shaking."},
        {"label": "Better Luck Next Time", "type": "try_again", "multiplier": 0, "weight": 12, "tone": "ice", "hint": "Wrong answer = 0 points instead of -1. Break even!"},
        {"label": "Shield", "type": "shield", "multiplier": 0, "weight": 9, "tone": "ice", "hint": "Block the negative. Turn failure into zero."},
        {"label": "Wildfire", "type": "wildfire", "multiplier": None, "weight": 10, "tone": "fire", "hint": "Chaos erupts. Random 2–5× multiplier drawn at use."},
        {"label": "Double or Nothing", "type": "double_nothing", "multiplier": None, "weight": 6, "tone": "fire", "hint": "50/50 gamble: 2× or lose everything. High risk!"},
        {"label": "Reverse", "type": "reverse", "multiplier": None, "weight": 5, "tone": "acid", "hint": "Flip the script. Losses become wins, wins get +1."},
        {"label": "Free Spin", "type": "free_spin", "multiplier": 0, "weight": 4, "tone": "gold", "hint": "Skip the cooldown. Spin again today!"},
    ]


def _team_match_query(team: str):
    return Match.query.filter(or_(Match.team_a == team, Match.team_b == team))

def _get_recent_history():
    import json
    history_map = {}
    recent = Match.query.filter(Match.status == "completed").order_by(Match.start_time.desc()).limit(5).all()
    recent.reverse()
    if not recent:
        return {}
    standings = MatchStanding.query.filter(MatchStanding.match_id.in_([m.id for m in recent])).all()
    pts_map = {(s.match_id, s.user_id): s.match_points for s in standings}
    for u in User.query.filter_by(is_admin=False).all():
        history = []
        for m in recent:
            pts = pts_map.get((m.id, u.id))
            if pts is not None:
                history.append({"date": m.start_time_ist.strftime("%d %b"), "points": pts})
        history_map[u.id] = json.dumps(history)
    return history_map


def _build_profile_history(user: User, limit: int | None = None):
    history = {}
    standings = MatchStanding.query.filter_by(user_id=user.id).all()
    winner_map = {entry.match_id: entry.winner_points == 1 for entry in standings}
    for vote in user.votes:
        match = vote.poll.match
        if match.id not in history:
            history[match.id] = {
                "label": match.display_name,
                "date": match.start_time,
                "points": 0,
                "winner": winner_map.get(match.id, False),
            }
        history[match.id]["points"] += vote.points

    history_list = sorted(history.values(), key=lambda item: item["date"])
    if limit is not None:
        return history_list[-limit:]
    return history_list


def _week_start() -> datetime.date:
    today = datetime.utcnow().date()
    return today - timedelta(days=today.weekday())


@main_bp.route("/")
@login_required
def dashboard():
    update_match_statuses()
    if current_user.is_admin:
        return redirect(url_for("admin.admin_dashboard"))

    upcoming = (
        Match.query.filter(Match.status != "completed")
        .order_by(Match.start_time.asc())
        .all()
    )
    live_match = next((match for match in upcoming if match.status == "live"), None)
    next_upcoming = next((match for match in upcoming if match.status == "upcoming"), None)
    spotlight_match = live_match or next_upcoming
    total_points = sum(v.points for v in current_user.votes)
    total_votes = len(current_user.votes)
    match_points = {}
    for vote in current_user.votes:
        if not vote.poll:
            continue
        match_id = vote.poll.match_id
        match_points[match_id] = match_points.get(match_id, 0) + vote.points
    matches_played = len(match_points)
    avg_points = round(total_points / matches_played, 1) if matches_played else 0
    hit_rate = 0
    if total_votes:
        hit_rate = round((len([v for v in current_user.votes if v.points > 0]) / total_votes) * 100)

    correct_votes = len([v for v in current_user.votes if v.points > 0])
    incorrect_votes = len([v for v in current_user.votes if v.points < 0])
    pending_votes = total_votes - correct_votes - incorrect_votes
    resolved_total = correct_votes + incorrect_votes
    accuracy = round((correct_votes / resolved_total) * 100) if resolved_total else 0
    avg_confidence = round(sum(v.confidence for v in current_user.votes) / total_votes, 2) if total_votes else 0
    high_confidence_picks = len([v for v in current_user.votes if v.confidence == 3])

    next_match = spotlight_match
    next_match_ts = next_match.start_time_ist_timestamp if next_match and next_match.status == "upcoming" else None

    rival = None
    rivals = User.query.filter(User.is_admin.is_(False), User.id != current_user.id).all()
    if rivals:
        rival = max(rivals, key=lambda user: sum(v.points for v in user.votes))
    rival_points = sum(v.points for v in rival.votes) if rival else 0

    streak_map = compute_user_streaks([current_user.id])
    current_streak = streak_map.get(current_user.id, {}).get("current", 0)
    best_streak = streak_map.get(current_user.id, {}).get("best", 0)

    trophies = _build_trophies(
        total_votes,
        total_points,
        hit_rate,
        matches_played,
        avg_points,
        high_confidence_picks,
        accuracy,
    )
    fun_badges = _build_fun_badges(
        current_streak,
        best_streak,
        accuracy,
        avg_confidence,
        high_confidence_picks,
        total_points,
    )

    # Check daily spin cooldown (24 hours)
    last_spin = RouletteSpin.query.filter_by(user_id=current_user.id).order_by(RouletteSpin.created_at.desc()).first()
    can_spin = True
    spin_reset_ts = None
    spin_reset_label = None
    if last_spin:
        time_since_spin = (datetime.utcnow() - last_spin.created_at).total_seconds()
        if time_since_spin < 86400:
            can_spin = False
            time_remaining = 86400 - int(time_since_spin)
            spin_reset_ts = int((datetime.utcnow() + timedelta(seconds=time_remaining)).timestamp())
            hours = time_remaining // 3600
            minutes = (time_remaining % 3600) // 60
            spin_reset_label = f"{hours}h {minutes}m"

    # Get all active boosts (multiple boosts allowed)
    active_boosts = UserBoost.query.filter_by(user_id=current_user.id, status="active").all()
    roulette_options = _roulette_options()

    week_cutoff = datetime.utcnow() - timedelta(days=7)
    recent_matches = (
        Match.query.filter(Match.status == "completed", Match.start_time >= week_cutoff)
        .order_by(Match.start_time.desc())
        .all()
    )
    weekly_users = User.query.filter(User.is_admin.is_(False)).all()
    weekly_points = {user.id: 0 for user in weekly_users}
    for match in recent_matches:
        poll_ids = [poll.id for poll in match.polls]
        if not poll_ids:
            continue
        for vote in Vote.query.filter(Vote.poll_id.in_(poll_ids)).all():
            if vote.user_id in weekly_points:
                weekly_points[vote.user_id] += vote.points

    weekly_leaderboard = []
    for user in weekly_users:
        weekly_leaderboard.append({"user": user, "points": weekly_points.get(user.id, 0)})
    weekly_leaderboard.sort(key=lambda item: item["points"], reverse=True)
    weekly_top = weekly_leaderboard[0] if weekly_leaderboard else None

    win_rows = (
        db.session.query(
            MatchStanding.user_id,
            db.func.coalesce(db.func.sum(MatchStanding.winner_points), 0).label("wins"),
        )
        .group_by(MatchStanding.user_id)
        .all()
    )
    win_map = {row.user_id: int(row.wins) for row in win_rows}
    streak_map = compute_user_streaks([user.id for user in weekly_users])
    history_map = _get_recent_history()
    leaderboard_data = []
    for user in weekly_users:
        points = sum(v.points for v in user.votes)
        wins = win_map.get(user.id, 0)
        user_streak = streak_map.get(user.id, {})
        leaderboard_data.append({
            "user": user,
            "points": points,
            "wins": wins,
            "history": history_map.get(user.id, "[]"),
            "streak": user_streak.get("current", 0),
        })
    leaderboard_data.sort(key=lambda item: (item["wins"], item["points"]), reverse=True)

    opponents = User.query.filter(User.is_admin.is_(False), User.id != current_user.id).order_by(User.username.asc()).all()
    available_matches = [match for match in upcoming if match.status in {"upcoming", "live"}]
    battle_rows = (
        Battle.query.filter((Battle.challenger_id == current_user.id) | (Battle.opponent_id == current_user.id))
        .order_by(Battle.created_at.desc())
        .all()
    )
    battle_cards = []
    for battle in battle_rows:
        match = battle.match
        challenger_points = None
        opponent_points = None
        result = "pending"
        if match and match.status == "completed":
            challenger_standing = MatchStanding.query.filter_by(match_id=match.id, user_id=battle.challenger_id).first()
            opponent_standing = MatchStanding.query.filter_by(match_id=match.id, user_id=battle.opponent_id).first()
            challenger_points = challenger_standing.match_points if challenger_standing else 0
            opponent_points = opponent_standing.match_points if opponent_standing else 0
            if challenger_points > opponent_points:
                result = "challenger"
            elif opponent_points > challenger_points:
                result = "opponent"
            else:
                result = "draw"

        battle_cards.append({
            "battle": battle,
            "match": match,
            "result": result,
            "challenger_points": challenger_points,
            "opponent_points": opponent_points,
        })

    return render_template(
        "dashboard.html",
        matches=upcoming,
        total_points=total_points,
        total_votes=total_votes,
        matches_played=matches_played,
        next_match=next_match,
        next_match_ts=next_match_ts,
        spotlight_match=spotlight_match,
        badges=trophies,
        leaderboard=leaderboard_data[:5],
        correct_votes=correct_votes,
        incorrect_votes=incorrect_votes,
        pending_votes=pending_votes,
        accuracy=accuracy,
        avg_confidence=avg_confidence,
        high_confidence_picks=high_confidence_picks,
        current_streak=current_streak,
        best_streak=best_streak,
        active_boosts=active_boosts,
        can_spin=can_spin,
        roulette_options=roulette_options,
        spin_reset_ts=spin_reset_ts,
        spin_reset_label=spin_reset_label,
        weekly_top=weekly_top,
        weekly_leaderboard=weekly_leaderboard[:3],
        opponents=opponents,
        available_matches=available_matches,
        battle_cards=battle_cards,
    )


@main_bp.route("/match/<int:match_id>")
@login_required
def match_detail(match_id):
    update_match_statuses()
    match = Match.query.get_or_404(match_id)
    polls = Poll.query.filter_by(match_id=match_id).all()
    user_votes = {v.poll_id: v for v in Vote.query.filter_by(user_id=current_user.id).all()}
    active_boosts = UserBoost.query.filter_by(user_id=current_user.id, status="active").all()
    
    # Build a map of which boosts are applied to which votes (supports multiple votes per boost)
    vote_boosts = {}
    for boost in UserBoost.query.filter_by(user_id=current_user.id).all():
        # Check both applied_vote_ids (new) and applied_vote_id (legacy support)
        applied_ids = boost.applied_vote_ids if boost.applied_vote_ids else []
        if boost.applied_vote_id and boost.applied_vote_id not in applied_ids:
            applied_ids.append(boost.applied_vote_id)
        
        # Map each vote ID to this boost
        for vote_id in applied_ids:
            vote_boosts[vote_id] = boost
    
    return render_template(
        "match.html",
        match=match,
        polls=polls,
        user_votes=user_votes,
        active_boosts=active_boosts,
        vote_boosts=vote_boosts,
    )


@main_bp.route("/my-votes")
@login_required
def my_votes():
    update_match_statuses()
    votes = (
        Vote.query.filter_by(user_id=current_user.id)
        .join(Poll, Poll.id == Vote.poll_id)
        .join(Match, Match.id == Poll.match_id)
        .order_by(Match.start_time.desc())
        .all()
    )
    return render_template("my_votes.html", votes=votes)


@main_bp.route("/leaderboard")
@login_required
def leaderboard():
    update_match_statuses()
    users = User.query.filter_by(is_admin=False).all()
    win_rows = (
        db.session.query(
            MatchStanding.user_id,
            db.func.coalesce(db.func.sum(MatchStanding.winner_points), 0).label("wins"),
        )
        .group_by(MatchStanding.user_id)
        .all()
    )
    win_map = {row.user_id: int(row.wins) for row in win_rows}
    streak_map = compute_user_streaks([user.id for user in users])
    history_map = _get_recent_history()
    leaderboard_data = []
    for user in users:
        points = sum(v.points for v in user.votes)
        wins = win_map.get(user.id, 0)
        leaderboard_data.append({
            "user": user,
            "points": points,
            "wins": wins,
            "history": history_map.get(user.id, "[]"),
            "streak": streak_map.get(user.id, {}).get("current", 0),
        })
    leaderboard_data.sort(key=lambda item: (item["wins"], item["points"]), reverse=True)
    return render_template("leaderboard.html", leaderboard=leaderboard_data)


@main_bp.route("/match-standings")
@login_required
def match_standings():
    update_match_statuses()
    matches = Match.query.filter(Match.status == "completed").order_by(Match.start_time.desc()).all()
    standings_payload = []
    for match in matches:
        update_match_standings(match.id)
        entries = (
            MatchStanding.query.filter_by(match_id=match.id)
            .join(User, User.id == MatchStanding.user_id)
            .order_by(
                MatchStanding.winner_points.desc(),
                MatchStanding.match_points.desc(),
                User.username.asc(),
            )
            .all()
        )
        standings_payload.append({"match": match, "entries": entries})

    return render_template(
        "match_standings.html",
        standings=standings_payload,
    )


@main_bp.route("/results")
@login_required
def results():
    update_match_statuses()
    matches = Match.query.filter(Match.status == "completed").order_by(Match.start_time.asc()).all()
    results_payload = []
    for match in matches:
        update_match_standings(match.id)
        polls = match.polls
        poll_ids = [poll.id for poll in polls]
        user_votes = []
        if poll_ids:
            user_votes = Vote.query.filter(
                Vote.user_id == current_user.id,
                Vote.poll_id.in_(poll_ids),
            ).all()

        total_votes = len(user_votes)
        correct_votes = len([vote for vote in user_votes if vote.points > 0])
        incorrect_votes = len([vote for vote in user_votes if vote.points < 0])
        pending_votes = total_votes - correct_votes - incorrect_votes
        accuracy = round((correct_votes / (correct_votes + incorrect_votes)) * 100) if (correct_votes + incorrect_votes) else 0

        standings = (
            MatchStanding.query.filter_by(match_id=match.id)
            .join(User, User.id == MatchStanding.user_id)
            .order_by(
                MatchStanding.match_points.desc(),
                User.username.asc(),
            )
            .all()
        )
        rank_lookup = {entry.user_id: idx + 1 for idx, entry in enumerate(standings)}
        points_lookup = {entry.user_id: entry.match_points for entry in standings}
        match_points = points_lookup.get(current_user.id, 0)
        match_rank = rank_lookup.get(current_user.id)

        biggest_win = None
        biggest_miss = None
        if user_votes:
            best_vote = max(user_votes, key=lambda vote: vote.points)
            if best_vote.points > 0:
                biggest_win = {
                    "question": best_vote.poll.question,
                    "option": best_vote.option,
                    "points": best_vote.points,
                }
            worst_vote = min(user_votes, key=lambda vote: vote.points)
            if worst_vote.points < 0:
                biggest_miss = {
                    "question": worst_vote.poll.question,
                    "option": worst_vote.option,
                    "points": worst_vote.points,
                }

        entries = (
            MatchStanding.query.filter_by(match_id=match.id)
            .join(User, User.id == MatchStanding.user_id)
            .order_by(
                MatchStanding.winner_points.desc(),
                MatchStanding.match_points.desc(),
                User.username.asc(),
            )
            .all()
        )
        winners = [entry for entry in entries if entry.winner_points == 1]
        winner_cards = []
        for entry in winners:
            winner_cards.append(
                {
                    "username": entry.user.username,
                    "points": entry.match_points,
                }
            )
        spotlight = winner_cards[0] if winner_cards else None
        results_payload.append({
            "match": match,
            "spotlight": spotlight,
            "winners": winner_cards,
            "user_highlight": {
                "total": total_votes,
                "correct": correct_votes,
                "incorrect": incorrect_votes,
                "pending": pending_votes,
                "accuracy": accuracy,
                "biggest_win": biggest_win,
                "biggest_miss": biggest_miss,
                "match_points": match_points,
                "match_rank": match_rank,
            },
        })

    results_payload.reverse()
    return render_template("results.html", results=results_payload, now=datetime.utcnow())

@main_bp.route("/standings")
@login_required
def standings():
    update_match_statuses()

    users = User.query.filter_by(is_admin=False).all()
    win_rows = (
        db.session.query(
            MatchStanding.user_id,
            db.func.coalesce(db.func.sum(MatchStanding.winner_points), 0).label("wins"),
        )
        .group_by(MatchStanding.user_id)
        .all()
    )
    win_map = {row.user_id: int(row.wins) for row in win_rows}
    streak_map = compute_user_streaks([user.id for user in users])
    history_map = _get_recent_history()
    leaderboard_data = []
    for user in users:
        points = sum(v.points for v in user.votes)
        wins = win_map.get(user.id, 0)
        leaderboard_data.append({
            "user": user,
            "points": points,
            "wins": wins,
            "history": history_map.get(user.id, "[]"),
            "streak": streak_map.get(user.id, {}).get("current", 0),
        })
    leaderboard_data.sort(key=lambda item: (item["wins"], item["points"]), reverse=True)

    matches = Match.query.filter(Match.status == "completed").order_by(Match.start_time.desc()).all()
    standings_payload = []
    for match in matches:
        update_match_standings(match.id)
        entries = (
            MatchStanding.query.filter_by(match_id=match.id)
            .join(User, User.id == MatchStanding.user_id)
            .order_by(
                MatchStanding.winner_points.desc(),
                MatchStanding.match_points.desc(),
                User.username.asc(),
            )
            .all()
        )
        standings_payload.append({"match": match, "entries": entries})

    return render_template(
        "standings.html",
        leaderboard=leaderboard_data,
        standings=standings_payload,
    )


@main_bp.route("/teams")
@login_required
def teams():
    update_match_statuses()
    team_cards = []
    for team in TEAMS:
        player_count = Player.query.filter_by(team=team).count()
        match_query = _team_match_query(team)
        upcoming = match_query.filter(Match.status != "completed").count()
        completed = match_query.filter(Match.status == "completed").count()
        team_cards.append({
            "name": team,
            "players": player_count,
            "upcoming": upcoming,
            "completed": completed,
        })

    return render_template("teams.html", teams=team_cards)


@main_bp.route("/teams/<path:team_name>")
@login_required
def team_detail(team_name):
    update_match_statuses()
    decoded = unquote(team_name)
    if decoded not in TEAMS:
        flash("Team not found.", "error")
        return redirect(url_for("main.teams"))

    roster = Player.query.filter_by(team=decoded).order_by(Player.role.asc(), Player.name.asc()).all()
    player_names = [player.name for player in roster]

    pick_rows = []
    if player_names:
        pick_rows = (
            db.session.query(
                Vote.option.label("name"),
                func.count(Vote.id).label("picks"),
                func.sum(case((Vote.points > 0, 1), else_=0)).label("correct"),
            )
            .filter(Vote.option.in_(player_names))
            .group_by(Vote.option)
            .all()
        )

    pick_map = {row.name: {"picks": int(row.picks or 0), "correct": int(row.correct or 0)} for row in pick_rows}
    player_stats = []
    for player in roster:
        stat = pick_map.get(player.name, {"picks": 0, "correct": 0})
        picks = stat["picks"]
        correct = stat["correct"]
        accuracy = round((correct / picks) * 100) if picks else 0
        player_stats.append({
            "name": player.name,
            "role": player.role or "",
            "picks": picks,
            "correct": correct,
            "accuracy": accuracy,
        })

    top_picks = sorted(player_stats, key=lambda item: item["picks"], reverse=True)[:5]
    accuracy_pool = [item for item in player_stats if item["picks"] >= 3]
    top_accuracy = sorted(accuracy_pool, key=lambda item: item["accuracy"], reverse=True)[:5]

    match_query = _team_match_query(decoded)
    upcoming_matches = (
        match_query.filter(Match.status != "completed")
        .order_by(Match.start_time.asc())
        .limit(4)
        .all()
    )
    recent_matches = (
        match_query.filter(Match.status == "completed")
        .order_by(Match.start_time.desc())
        .limit(4)
        .all()
    )

    roster_by_role = {role: [] for role in ROLES}
    for player in roster:
        roster_by_role.setdefault(player.role or "Other", []).append(player)

    return render_template(
        "team_detail.html",
        team_name=decoded,
        roster=roster,
        roster_by_role=roster_by_role,
        player_stats=player_stats,
        top_picks=top_picks,
        top_accuracy=top_accuracy,
        upcoming_matches=upcoming_matches,
        recent_matches=recent_matches,
    )

@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    update_match_statuses()
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        avatar_file = request.files.get("avatar")

        if not username:
            flash("Display name is required.", "error")
            return redirect(url_for("main.profile"))

        if username != current_user.username:
            if User.query.filter_by(username=username).first():
                flash("That name is already taken.", "error")
                return redirect(url_for("main.profile"))
            current_user.username = username

        if avatar_file and avatar_file.filename:
            filename = secure_filename(avatar_file.filename)
            ext = os.path.splitext(filename)[1].lower()
            if ext not in {".png", ".jpg", ".jpeg", ".webp"}:
                flash("Avatar must be a PNG, JPG, or WEBP file.", "error")
                return redirect(url_for("main.profile"))

            new_name = f"{uuid4().hex}{ext}"
            save_path = os.path.join(current_app.config["UPLOAD_FOLDER"], new_name)
            avatar_file.save(save_path)
            current_user.avatar_path = new_name

        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("main.profile"))

    history_list = _build_profile_history(current_user)
    labels = [item["label"] for item in history_list]
    points = [item["points"] for item in history_list]
    # flags indicating whether the user won that match (used to mark chart points)
    wins = [bool(item.get("winner", False)) for item in history_list]
    # debug log: labels, points and wins lengths/values
    try:
        current_app.logger.debug(f"profile chart labels={labels}")
        current_app.logger.debug(f"profile chart points={points}")
        current_app.logger.debug(f"profile chart wins={wins}")
    except Exception:
        pass

    total_points = sum(v.points for v in current_user.votes)
    total_votes = len(current_user.votes)
    completed_history = [item for item in history_list if item["points"] != 0]
    matches_played = len(completed_history)
    avg_points = round(total_points / matches_played, 1) if matches_played else 0
    win_matches = len([item for item in completed_history if item.get("winner")])
    loss_matches = matches_played - win_matches
    win_rate = round((win_matches / matches_played) * 100) if matches_played else 0
    best_match = max(completed_history, key=lambda item: item["points"]) if completed_history else None
    worst_match = min(completed_history, key=lambda item: item["points"]) if completed_history else None
    recent_window = completed_history[-3:]
    prior_window = completed_history[-6:-3]
    recent_avg_points = round(sum(item["points"] for item in recent_window) / len(recent_window), 1) if recent_window else 0
    prior_avg_points = round(sum(item["points"] for item in prior_window) / len(prior_window), 1) if prior_window else 0
    momentum = round(recent_avg_points - prior_avg_points, 1) if prior_window else recent_avg_points
    hit_rate = 0
    if total_votes:
        hit_rate = round((len([v for v in current_user.votes if v.points > 0]) / total_votes) * 100)

    correct_votes = len([v for v in current_user.votes if v.points > 0])
    incorrect_votes = len([v for v in current_user.votes if v.points < 0])
    pending_votes = total_votes - correct_votes - incorrect_votes
    resolved_total = correct_votes + incorrect_votes
    accuracy = round((correct_votes / resolved_total) * 100) if resolved_total else 0
    avg_confidence = round(sum(v.confidence for v in current_user.votes) / total_votes, 2) if total_votes else 0
    confidence_counts = {
        1: len([v for v in current_user.votes if v.confidence == 1]),
        2: len([v for v in current_user.votes if v.confidence == 2]),
        3: len([v for v in current_user.votes if v.confidence == 3]),
    }
    high_confidence_picks = confidence_counts[3]
    streak_map = compute_user_streaks([current_user.id])
    current_streak = streak_map.get(current_user.id, {}).get("current", 0)
    best_streak = streak_map.get(current_user.id, {}).get("best", 0)

    confidence_stats = []
    for level in (1, 2, 3):
        picks = len([v for v in current_user.votes if v.confidence == level])
        correct = len([v for v in current_user.votes if v.confidence == level and v.points > 0])
        incorrect = len([v for v in current_user.votes if v.confidence == level and v.points < 0])
        accuracy_level = round((correct / (correct + incorrect)) * 100) if (correct + incorrect) else 0
        avg_points = round(
            (sum(v.points for v in current_user.votes if v.confidence == level) / picks),
            2,
        ) if picks else 0
        confidence_stats.append({
            "level": level,
            "picks": picks,
            "correct": correct,
            "incorrect": incorrect,
            "accuracy": accuracy_level,
            "avg_points": avg_points,
        })
    best_confidence = max(confidence_stats, key=lambda row: (row["accuracy"], row["picks"])) if confidence_stats else None

    team_picks = [v for v in current_user.votes if v.option in TEAMS]
    team_rows = {}
    for vote in team_picks:
        bucket = team_rows.setdefault(vote.option, {"picks": 0, "correct": 0, "points": 0})
        bucket["picks"] += 1
        if vote.points > 0:
            bucket["correct"] += 1
        bucket["points"] += vote.points

    team_accuracy = []
    for team, stats in team_rows.items():
        picks = stats["picks"]
        accuracy_team = round((stats["correct"] / picks) * 100) if picks else 0
        team_accuracy.append({
            "team": team,
            "picks": picks,
            "correct": stats["correct"],
            "accuracy": accuracy_team,
            "points": stats["points"],
        })
    team_accuracy.sort(key=lambda item: (item["accuracy"], item["picks"]), reverse=True)

    recent_form = []
    recent_matches = (
        Match.query.filter(Match.status == "completed")
        .order_by(Match.start_time.desc())
        .limit(8)
        .all()
    )
    match_ids = [match.id for match in recent_matches]
    if match_ids:
        votes_by_match = {}
        user_votes = (
            Vote.query.filter(Vote.user_id == current_user.id)
            .join(Poll, Poll.id == Vote.poll_id)
            .filter(Poll.match_id.in_(match_ids))
            .all()
        )
        for vote in user_votes:
            match_id = vote.poll.match_id
            bucket = votes_by_match.setdefault(match_id, {"total": 0, "correct": 0})
            bucket["total"] += 1
            if vote.points > 0:
                bucket["correct"] += 1

        for match in recent_matches:
            bucket = votes_by_match.get(match.id)
            if not bucket:
                continue
            accuracy_match = round((bucket["correct"] / bucket["total"]) * 100) if bucket["total"] else 0
            recent_form.append({
                "label": match.display_name,
                "date": match.start_time_ist.strftime("%d %b"),
                "accuracy": accuracy_match,
                "correct": bucket["correct"],
                "total": bucket["total"],
            })

    rival = None
    rivals = User.query.filter(User.is_admin.is_(False), User.id != current_user.id).all()
    if rivals:
        rival = max(rivals, key=lambda user: sum(v.points for v in user.votes))
    rival_points = sum(v.points for v in rival.votes) if rival else 0

    trophies = _build_trophies(
        total_votes,
        total_points,
        hit_rate,
        matches_played,
        avg_points,
        high_confidence_picks,
        accuracy,
    )
    fun_badges = _build_fun_badges(
        current_streak,
        best_streak,
        accuracy,
        avg_confidence,
        high_confidence_picks,
        total_points,
    )

    return render_template(
        "profile.html",
        history=history_list,
        chart_labels=labels,
        chart_points=points,
        total_points=total_points,
        matches_played=matches_played,
        avg_points=avg_points,
        win_matches=win_matches,
        loss_matches=loss_matches,
        win_rate=win_rate,
        best_match=best_match,
        worst_match=worst_match,
        recent_avg_points=recent_avg_points,
        prior_avg_points=prior_avg_points,
        momentum=momentum,
        best_confidence=best_confidence,
        hit_rate=hit_rate,
        rival=rival,
        rival_points=rival_points,
        trophies=trophies,
        fun_badges=fun_badges,
        correct_votes=correct_votes,
        incorrect_votes=incorrect_votes,
        pending_votes=pending_votes,
        accuracy=accuracy,
        avg_confidence=avg_confidence,
        confidence_counts=confidence_counts,
        confidence_stats=confidence_stats,
        team_accuracy=team_accuracy,
        recent_form=recent_form,
        current_streak=current_streak,
        best_streak=best_streak,
        recent_votes=(
            Vote.query.filter_by(user_id=current_user.id)
            .join(Poll, Poll.id == Vote.poll_id)
            .join(Match, Match.id == Poll.match_id)
            .order_by(Match.start_time.desc())
            .limit(5)
            .all()
        ),
        recent_results=(
            Match.query.filter(Match.status == "completed")
            .order_by(Match.start_time.desc())
            .limit(5)
            .all()
        ),
        chart_wins=wins,
    )


@main_bp.route("/profile/history")
@login_required
def profile_history():
    update_match_statuses()
    history_list = _build_profile_history(current_user)
    return render_template(
        "profile_history.html",
        history=history_list,
        total_points=sum(v.points for v in current_user.votes),
        current_user=current_user,
    )


@main_bp.route("/profile/export")
@login_required
def export_profile():
    votes = (
        Vote.query.filter_by(user_id=current_user.id)
        .join(Poll, Poll.id == Vote.poll_id)
        .join(Match, Match.id == Poll.match_id)
        .order_by(Match.start_time.asc())
        .all()
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
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
            match.display_name,
            match.start_time_ist.strftime("%Y-%m-%d %H:%M IST"),
            vote.poll.question,
            vote.option,
            vote.confidence,
            vote.points,
            result,
            match.status,
        ])

    filename = f"crictalx_votes_{datetime.utcnow().strftime('%Y%m%d')}.csv"
    response = current_app.response_class(output.getvalue(), mimetype="text/csv")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


@main_bp.route("/rewards")
@login_required
def rewards_inventory():
    """Display user's reward inventory"""
    # Get all boosts for current user
    active_boosts = UserBoost.query.filter_by(user_id=current_user.id, status="active").all()
    used_boosts = UserBoost.query.filter_by(user_id=current_user.id, status="used").order_by(UserBoost.used_at.desc()).all()
    expired_boosts = UserBoost.query.filter_by(user_id=current_user.id, status="expired").order_by(UserBoost.expires_at.desc()).all()
    
    # Boost type descriptions
    boost_descriptions = {
        "2x": "Double your points for correct picks",
        "3x": "Triple multiplier for maximum gains",
        "4x": "4× multiplier boost",
        "5x": "5× mega multiplier boost",
        "shield": "Blocks negatives—turn failure into zero",
        "wildfire": "Chaos: random multiplier between 2–5×",
        "double_nothing": "50/50 gamble: 2× or lose everything",
        "reverse": "Flip the script: losses become wins",
        "try_again": "Wrong answer gets 0 points instead of -1",
        "free_spin": "Get another free roulette spin"
    }
    
    return render_template(
        "rewards_inventory.html",
        active_boosts=active_boosts,
        used_boosts=used_boosts,
        expired_boosts=expired_boosts,
        boost_descriptions=boost_descriptions,
        current_user=current_user,
    )


@main_bp.route("/roulette/spin", methods=["POST"])
@login_required
def roulette_spin():
    if current_user.is_admin:
        flash("Admins cannot spin.", "error")
        return redirect(url_for("main.dashboard"))

    # Check 24-hour cooldown (daily spin)
    last_spin = RouletteSpin.query.filter_by(user_id=current_user.id).order_by(RouletteSpin.created_at.desc()).first()
    if last_spin and (datetime.utcnow() - last_spin.created_at).total_seconds() < 86400:
        time_remaining = 86400 - int((datetime.utcnow() - last_spin.created_at).total_seconds())
        hours = time_remaining // 3600
        minutes = (time_remaining % 3600) // 60
        flash(f"You can spin again in {hours}h {minutes}m.", "error")
        return redirect(url_for("main.dashboard"))

    roulette_options = _roulette_options()
    reward_option = random.choices(roulette_options, weights=[option["weight"] for option in roulette_options], k=1)[0]
    reward = f'{reward_option["label"]} (available to use)'
    expires_at = datetime.utcnow() + timedelta(days=7)
    boost = UserBoost(user_id=current_user.id, boost_type=reward_option["type"], multiplier=reward_option["multiplier"], expires_at=expires_at, status="active")
    spin = RouletteSpin(user_id=current_user.id, boost_type=reward_option["type"], reward=reward)
    db.session.add(spin)
    db.session.add(boost)
    db.session.commit()

    flash(f'Roulette landed on {reward_option["label"]}! You can use this boost on any poll in the next 7 days.', "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/battle/create", methods=["POST"])
@login_required
def create_battle():
    if current_user.is_admin:
        flash("Admins cannot create battles.", "error")
        return redirect(url_for("main.dashboard"))

    opponent_id = request.form.get("opponent_id", type=int)
    match_id = request.form.get("match_id", type=int)
    if not opponent_id or not match_id:
        flash("Select an opponent and match.", "error")
        return redirect(url_for("main.dashboard"))

    if opponent_id == current_user.id:
        flash("You cannot challenge yourself.", "error")
        return redirect(url_for("main.dashboard"))

    opponent = User.query.get_or_404(opponent_id)
    if opponent.is_admin:
        flash("You can only challenge players.", "error")
        return redirect(url_for("main.dashboard"))

    match = Match.query.get_or_404(match_id)
    if match.status == "completed":
        flash("Choose an upcoming match.", "error")
        return redirect(url_for("main.dashboard"))

    existing = Battle.query.filter(
        Battle.match_id == match_id,
        ((Battle.challenger_id == current_user.id) & (Battle.opponent_id == opponent_id))
        | ((Battle.challenger_id == opponent_id) & (Battle.opponent_id == current_user.id)),
        Battle.status.in_(["pending", "active"]),
    ).first()
    if existing:
        flash("A battle already exists for this match.", "error")
        return redirect(url_for("main.dashboard"))

    battle = Battle(
        challenger_id=current_user.id,
        opponent_id=opponent_id,
        match_id=match_id,
        status="pending",
    )
    db.session.add(battle)
    db.session.commit()
    flash("Battle invite sent.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/battle/<int:battle_id>/accept", methods=["POST"])
@login_required
def accept_battle(battle_id):
    battle = Battle.query.get_or_404(battle_id)
    if battle.opponent_id != current_user.id:
        flash("You are not allowed to accept this battle.", "error")
        return redirect(url_for("main.dashboard"))

    if battle.status != "pending":
        flash("Battle is not pending.", "error")
        return redirect(url_for("main.dashboard"))

    battle.status = "active"
    battle.accepted_at = datetime.utcnow()
    db.session.commit()
    flash("Battle accepted.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/battle/<int:battle_id>/cancel", methods=["POST"])
@login_required
def cancel_battle(battle_id):
    battle = Battle.query.get_or_404(battle_id)
    if battle.challenger_id != current_user.id and battle.opponent_id != current_user.id:
        flash("You are not allowed to cancel this battle.", "error")
        return redirect(url_for("main.dashboard"))

    if battle.status == "completed":
        flash("Battle already completed.", "error")
        return redirect(url_for("main.dashboard"))

    battle.status = "canceled"
    db.session.commit()
    flash("Battle canceled.", "success")
    return redirect(url_for("main.dashboard"))


@main_bp.route("/about")
def about():
    return render_template("about.html")


@main_bp.route("/faq")
def faq():
    faq_items = [
        {
            "question": "How does the polling system work?",
            "answer": "Players predict match outcomes by voting on polls. Each poll covers a specific prediction (e.g., team winner, top scorer). You earn points for correct predictions and can apply boosts to multiply your scores."
        },
        {
            "question": "How are points calculated?",
            "answer": "Correct predictions earn positive points based on your confidence level (1×, 2×, or 3×). Wrong predictions deduct points. Applied boosts multiply your scores accordingly—except for special boosts like Shield or Try Again."
        },
        {
            "question": "When can I vote on polls?",
            "answer": "You can vote on polls anytime before the match starts. Once the match begins, voting closes. Check the match start time (IST) to plan your votes."
        },
        {
            "question": "What happens if I miss a match?",
            "answer": "Missing a match means no votes recorded for that match. It doesn't affect your overall stats—just participate in future matches to build your streak and climb the leaderboard."
        },
        {
            "question": "How does the leaderboard work?",
            "answer": "The leaderboard ranks players by total wins and points across all matches. Your weekly rank resets every week. Climb by winning matches consistently and maintaining high accuracy."
        },
        {
            "question": "What are boosts?",
            "answer": "Boosts are special power-ups you earn from the daily roulette spin. Each boost has unique mechanics—multipliers (2×, 3×, etc.), defensive shields, chaotic wildcards, or utility rewards like free spins."
        },
        {
            "question": "How does the daily roulette spin work?",
            "answer": "Spin once every 24 hours to randomly earn a boost from 10 different reward types. After claiming a boost, you can manually apply it to one poll before it expires (7 days)."
        },
        {
            "question": "Can I use multiple boosts?",
            "answer": "Yes! You can have multiple active boosts in your inventory at once. You can apply a different boost to each poll you vote on (one boost per poll max)."
        },
        {
            "question": "What's the difference between all the boosts?",
            "answer": "Multipliers (2×, 3×, 4×, 5×) scale your points. Shield/Try Again protect against losses. Wildfire randomly picks a multiplier. Double or Nothing is a 50/50 gamble. Reverse flips losses to wins. Free Spin unlocks another spin today."
        },
        {
            "question": "How does Weekly MVP work?",
            "answer": "Weekly MVP tracks the highest rolling score across the last 7 days. It sits at the top of the dashboard so the current form leader always gets priority."
        },
    ]
    return render_template("faq.html", faq_items=faq_items)


@main_bp.route("/contact")
def contact():
    return render_template("contact.html")