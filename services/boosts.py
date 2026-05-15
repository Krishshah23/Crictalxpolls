from datetime import datetime
import random
from models import db
from models.user_boost import UserBoost


def apply_boost(vote) -> None:
    # Find boost that was pre-selected for this vote
    # Check both applied_vote_id (legacy) and applied_vote_ids (new multi-vote support)
    boost = UserBoost.query.filter_by(user_id=vote.user_id, applied_vote_id=vote.id).first()
    
    if not boost:
        # Check if this vote is in the applied_vote_ids list
        all_boosts = UserBoost.query.filter_by(user_id=vote.user_id).all()
        for b in all_boosts:
            if vote.id in (b.applied_vote_ids or []):
                boost = b
                break
    
    if not boost:
        return

    if boost.status != "active":
        return

    if boost.expires_at and boost.expires_at < datetime.utcnow():
        boost.status = "expired"
        db.session.add(boost)
        return

    # Handle special boost types
    if boost.boost_type == "try_again":
        # Wrong answer gets 0 points instead of -1
        if vote.points < 0:
            vote.points = 0
    elif boost.boost_type == "shield":
        # Blocks negatives—turn failure into zero
        if vote.points < 0:
            vote.points = 0
    elif boost.boost_type == "wildfire":
        # Chaos: random multiplier between 2–5×
        multipliers = [2, 2.5, 3, 3.5, 4, 5]
        chosen_multiplier = random.choice(multipliers)
        if vote.points > 0:
            vote.points = vote.points * chosen_multiplier
    elif boost.boost_type == "double_nothing":
        # 50/50 gamble: 2× or lose everything
        if random.random() < 0.5:
            # Win the gamble: 2× multiplier
            if vote.points > 0:
                vote.points = vote.points * 2
        else:
            # Lose the gamble: all points gone
            vote.points = 0
    elif boost.boost_type == "reverse":
        # Flip the script: losses become wins, wins get +1
        if vote.points < 0:
            vote.points = abs(vote.points)  # Losses become wins
        elif vote.points > 0:
            vote.points += 1  # Wins get bonus point
    elif boost.boost_type == "free_spin":
        # Free Spin: marked for special handling, unlock another spin
        # Will be processed elsewhere to grant immediate spin access
        pass
    else:
        # Multiply points for standard multiplier types (2x, 3x, 4x, 5x)
        if vote.points > 0:
            vote.points *= max(boost.multiplier, 1)

    # Mark boost as used
    boost.status = "used"
    boost.used_at = datetime.utcnow()
    db.session.add(boost)
