"""Parse specialist vote JSON into AgentVote."""
from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from ..schemas import AgentVote
from .inference import extract_json_object, parse_goals

ROUND1_ISOLATION = """
ROUND 1 RULES (mandatory):
- You have NOT seen other specialists' votes, probabilities, scores, or reasoning.
- Do not guess or infer what other agents think. Use only your data slice and MCP tools.
- When ready, call submit_vote or reply with ONLY the vote JSON.
"""


def prob_from_goals(team_a_goals: int, team_b_goals: int) -> float:
    if team_a_goals > team_b_goals:
        return 0.75
    if team_a_goals < team_b_goals:
        return 0.25
    return 0.5


def is_parse_error(vote: AgentVote) -> bool:
    return vote.key_signal == "parse_error"


def vote_text_from_messages(messages: list) -> str:
    """Find vote JSON in ReAct message history (final reply or submit_vote tool)."""
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == "submit_vote":
            content = msg.content
            if content:
                return str(content)
        if isinstance(msg, AIMessage):
            text = str(msg.content or "")
            if extract_json_object(text):
                return text
            for tc in getattr(msg, "tool_calls", None) or []:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                if name != "submit_vote":
                    continue
                args = tc.get("args") if isinstance(tc, dict) else getattr(tc, "args", {})
                if isinstance(args, dict) and args:
                    return json.dumps(args)
    return ""


def vote_from_payload(data: dict, role: str, round: int) -> AgentVote:
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
            reasoning=(text or "")[:200],
            uncertainty_flag=True,
            round=round,
        )
    return vote_from_payload(data, role, round)
