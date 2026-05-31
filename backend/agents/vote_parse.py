"""Parse specialist vote JSON into AgentVote."""
from __future__ import annotations

from ..schemas import AgentVote
from .inference import extract_json_object, parse_goals


def prob_from_goals(team_a_goals: int, team_b_goals: int) -> float:
    if team_a_goals > team_b_goals:
        return 0.75
    if team_a_goals < team_b_goals:
        return 0.25
    return 0.5


def parse_vote(text: str, role: str, round: int) -> AgentVote:
    data = extract_json_object(text)
    if not data:
        return AgentVote(
            role=role,
            team_a_goals=0,
            team_b_goals=0,
            probability=0.5,
            confidence=0.5,
            key_signal="parse_error",
            reasoning=text[:200],
            uncertainty_flag=True,
            round=round,
        )
    goals_a, goals_b = parse_goals(data)
    prob = data.get("probability")
    probability = (
        float(prob) if prob is not None else prob_from_goals(goals_a, goals_b)
    )
    return AgentVote(
        role=role,
        team_a_goals=goals_a,
        team_b_goals=goals_b,
        probability=probability,
        confidence=float(data.get("confidence", 0.5)),
        key_signal=str(data.get("key_signal", "")),
        reasoning=str(data.get("reasoning", "")),
        uncertainty_flag=bool(data.get("uncertainty_flag", False)),
        round=round,
    )
