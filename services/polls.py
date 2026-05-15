from models.poll import Poll
from models.player import Player
from services.ipl_data import ROLE_GROUPS


def _players_for_team(team: str, roles: list[str] | None = None) -> list[str]:
    query = Player.query.filter_by(team=team)
    if roles:
        query = query.filter(Player.role.in_(roles))
    return [player.name for player in query.order_by(Player.name.asc()).all()]


def build_standard_polls(match, squad_a=None, squad_b=None):
    team_a = match.team_a
    team_b = match.team_b

    if squad_a is None:
        squad_a = _players_for_team(team_a)
    if squad_b is None:
        squad_b = _players_for_team(team_b)

    squad_a = squad_a or ["Player A1", "Player A2", "Player A3", "Player A4"]
    squad_b = squad_b or ["Player B1", "Player B2", "Player B3", "Player B4"]

    squad_a_bat = _players_for_team(
        team_a, ROLE_GROUPS["batsmen"] + ROLE_GROUPS["all_rounders"]
    ) or squad_a
    squad_b_bat = _players_for_team(
        team_b, ROLE_GROUPS["batsmen"] + ROLE_GROUPS["all_rounders"]
    ) or squad_b
    squad_a_bowl = _players_for_team(team_a, ROLE_GROUPS["bowlers"] + ROLE_GROUPS["all_rounders"]) or squad_a
    squad_b_bowl = _players_for_team(team_b, ROLE_GROUPS["bowlers"] + ROLE_GROUPS["all_rounders"]) or squad_b

    return [
        Poll(match_id=match.id, question="Who will win the toss", options=[team_a, team_b], is_toss_poll=True),
        Poll(match_id=match.id, question=f"{team_a} won the toss", options=["Bowl", "Bat"], is_toss_poll=True),
        Poll(match_id=match.id, question=f"{team_b} won the toss", options=["Bowl", "Bat"], is_toss_poll=True),
        Poll(match_id=match.id, question=f"P1 wickets for {team_a}", options=["0", "1", "2", "3", "3+"]),
        Poll(match_id=match.id, question=f"P1 runs for {team_a}", options=["1-40", "41-60", "61-70", "71+"]),
        Poll(match_id=match.id, question=f"Highest run scorer for {team_a}", options=squad_a_bat),
        Poll(match_id=match.id, question=f"Highest wicket taker for {team_a}", options=squad_a_bowl),
        Poll(match_id=match.id, question=f"Economical bowler for {team_a}", options=squad_a_bowl),
        Poll(match_id=match.id, question=f"How many extras will {team_a} give", options=["0-5", "6-10", "11-15", "16-20", "21+"]),
        Poll(match_id=match.id, question=f"50's for {team_a}", options=["0", "1", "2", "2+"]),
        Poll(match_id=match.id, question=f"100 for {team_a}", options=["0", "1", "1+"]),
        Poll(
            match_id=match.id,
            question=f"Projected score for {team_a}",
            options=["1-100", "101-125", "126-150", "151-175", "176-200", "201-220", "221-235", "235-250", "251+"],
        ),
        Poll(match_id=match.id, question=f"P1 wickets for {team_b}", options=["0", "1", "2", "3", "3+"]),
        Poll(match_id=match.id, question=f"P1 runs for {team_b}", options=["1-40", "41-60", "61-70", "71+"]),
        Poll(match_id=match.id, question=f"Highest run scorer for {team_b}", options=squad_b_bat),
        Poll(match_id=match.id, question=f"Highest wicket taker for {team_b}", options=squad_b_bowl),
        Poll(match_id=match.id, question=f"Economical bowler for {team_b}", options=squad_b_bowl),
        Poll(match_id=match.id, question=f"How many extras will {team_b} give", options=["0-5", "6-10", "11-15", "16-20", "21+"]),
        Poll(match_id=match.id, question=f"50's for {team_b}", options=["0", "1", "2", "2+"]),
        Poll(match_id=match.id, question=f"100 for {team_b}", options=["0", "1", "1+"]),
        Poll(
            match_id=match.id,
            question=f"Projected score for {team_b}",
            options=["1-100", "101-125", "126-150", "151-175", "176-200", "201-220", "221-240", "241-250", "251+"],
        ),
        Poll(match_id=match.id, question="Which team will hit more sixes", options=[team_a, team_b]),
        Poll(match_id=match.id, question="Who will win", options=[team_a, team_b]),
    ]
