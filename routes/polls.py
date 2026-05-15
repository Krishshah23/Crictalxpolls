from datetime import datetime, timedelta
from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db
from models.poll import Poll
from models.vote import Vote
from models.user_boost import UserBoost
from sqlalchemy.orm.attributes import flag_modified


polls_bp = Blueprint("polls", __name__)


@polls_bp.route("/poll/<int:poll_id>/vote", methods=["POST"])
@login_required
def vote(poll_id):
    poll = Poll.query.get_or_404(poll_id)
    match = poll.match

    if current_user.is_admin:
        flash("Admins cannot vote on polls.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    if match.has_started or not poll.is_active:
        flash("Polls are closed for this match.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    option = request.form.get("option")
    if not option:
        flash("Please select an option.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    existing = Vote.query.filter_by(user_id=current_user.id, poll_id=poll.id).first()
    if existing:
        existing.option = option
    else:
        db.session.add(Vote(user_id=current_user.id, poll_id=poll.id, option=option))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Error submitting vote. Please try again.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))
    
    flash("Vote submitted!", "success")
    return redirect(url_for("main.match_detail", match_id=match.id))


@polls_bp.route("/match/<int:match_id>/vote", methods=["POST"])
@login_required
def vote_match(match_id):
    match = Poll.query.filter_by(match_id=match_id).first_or_404().match

    if current_user.is_admin:
        flash("Admins cannot vote on polls.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    if match.has_started:
        flash("Polls are closed for this match.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    polls = Poll.query.filter_by(match_id=match_id).all()
    changes = 0
    selections = 0

    def _is_locked(poll: Poll) -> bool:
        lock_time = match.start_time - timedelta(minutes=30) if poll.is_toss_poll else match.start_time
        return poll.is_locked or datetime.utcnow() >= lock_time

    for poll in polls:
        if not poll.is_active:
            continue
        if _is_locked(poll):
            continue
        option = request.form.get(f"poll_{poll.id}")
        if not option:
            continue
        selections += 1
        if option not in poll.options:
            continue

        confidence_raw = request.form.get(f"confidence_{poll.id}", "1")
        try:
            confidence = int(confidence_raw)
        except ValueError:
            confidence = 1
        confidence = confidence if confidence in (1, 2, 3) else 1

        existing = Vote.query.filter_by(user_id=current_user.id, poll_id=poll.id).first()
        if existing:
            if existing.option != option:
                existing.option = option
                existing.confidence = confidence
                changes += 1
            vote = existing
        else:
            vote = Vote(user_id=current_user.id, poll_id=poll.id, option=option, confidence=confidence)
            db.session.add(vote)
            db.session.flush()
            changes += 1

        boost_raw = request.form.get(f"boost_{poll.id}", "")
        if boost_raw:
            try:
                boost_id = int(boost_raw)
            except ValueError:
                flash("Invalid boost selection.", "error")
                return redirect(url_for("main.match_detail", match_id=match.id))

            boost = UserBoost.query.filter_by(id=boost_id, user_id=current_user.id).first()
            if not boost or boost.status != "active":
                flash("That boost is no longer available.", "error")
                return redirect(url_for("main.match_detail", match_id=match.id))
            if boost.expires_at and boost.expires_at < datetime.utcnow():
                flash("That boost has expired.", "error")
                return redirect(url_for("main.match_detail", match_id=match.id))

            # Get the list of vote IDs this boost is applied to (supports multiple votes in same match)
            # Ensure applied_vote_ids is a list
            applied_ids = list(boost.applied_vote_ids) if boost.applied_vote_ids else []
            
            # Add this vote to the list if not already there
            if vote.id not in applied_ids:
                applied_ids.append(vote.id)
                boost.applied_vote_ids = applied_ids
                flag_modified(boost, "applied_vote_ids")  # Tell SQLAlchemy the JSON field changed
                # Also keep applied_vote_id for backward compatibility (set to latest)
                boost.applied_vote_id = vote.id
                db.session.add(boost)  # Explicitly mark for update
                changes += 1
            
            # Remove any OTHER boosts from this specific vote
            for other_boost in UserBoost.query.filter_by(user_id=current_user.id, status="active").all():
                if other_boost.id != boost.id and vote.id in (other_boost.applied_vote_ids or []):
                    new_ids = [vid for vid in other_boost.applied_vote_ids if vid != vote.id]
                    other_boost.applied_vote_ids = new_ids
                    flag_modified(other_boost, "applied_vote_ids")  # Tell SQLAlchemy the JSON field changed
                    if not new_ids:
                        other_boost.applied_vote_id = None
                    db.session.add(other_boost)  # Explicitly mark for update
                    changes += 1
        else:
            # User selected "No boost" - remove this vote from all boosts
            for boost in UserBoost.query.filter_by(user_id=current_user.id, status="active").all():
                if vote.id in (boost.applied_vote_ids or []):
                    new_ids = [vid for vid in boost.applied_vote_ids if vid != vote.id]
                    boost.applied_vote_ids = new_ids
                    flag_modified(boost, "applied_vote_ids")  # Tell SQLAlchemy the JSON field changed
                    if not new_ids:
                        boost.applied_vote_id = None
                    db.session.add(boost)  # Explicitly mark for update
                    changes += 1

    if selections == 0:
        flash("Pick at least one option before submitting.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))

    if changes == 0:
        flash("No changes to update.", "success")
        return redirect(url_for("main.match_detail", match_id=match.id))

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash("Error saving votes. Please try again.", "error")
        return redirect(url_for("main.match_detail", match_id=match.id))
    flash("Picks saved.", "success")
    return redirect(url_for("main.match_detail", match_id=match.id))