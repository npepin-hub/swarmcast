"""Research specialist — LangGraph pipeline → AgentVote."""
from __future__ import annotations

import asyncio

import weave

from ...config import settings
from ...schemas import AgentVote
from ..vote_parse import parse_vote
from .graph import compiled_research_graph
from .nodes import _finalize_research_vote, vote_from_ml_prediction
from .state import ResearchState
from .ml_log import research_ml_log
from .wc_model import ensure_model


def _initial_state(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int,
    group: str = "",
) -> ResearchState:
    return ResearchState(
        match_query=match_query,
        team_a=team_a,
        team_b=team_b,
        context=context,
        group=group,
        round=round,
        rephrased_question=match_query,
        research_brief="",
        audit_status="",
        revision_count=0,
        history=[],
        model_features={},
        model_prediction={},
    )


def _coerce_vote(raw: object) -> AgentVote | None:
    if isinstance(raw, AgentVote):
        return raw
    if isinstance(raw, dict):
        try:
            return AgentVote(**raw)
        except Exception:
            return None
    return None


def _state_from_result(base: ResearchState, result: dict) -> ResearchState:
    merged: ResearchState = dict(base)
    for key in (
        "match_query",
        "team_a",
        "team_b",
        "context",
        "round",
        "research_brief",
        "model_prediction",
        "model_features",
    ):
        if key in result and result[key] is not None:
            merged[key] = result[key]
    return merged


def _resolve_research_vote(state: ResearchState, result: dict) -> AgentVote:
    """Always apply ML baseline to probability (fixes UI stuck at 50%)."""
    pred = result.get("model_prediction") or {}
    round_num = int(state.get("round", 1))
    vote = _coerce_vote(result.get("vote"))

    if pred and vote:
        return _finalize_research_vote(_state_from_result(state, result), vote, pred)

    if pred:
        research_ml_log(
            "Vote node missing — using ML-only vote",
            payload={"probability_team_a": pred.get("probability_team_a")},
        )
        brief = str(result.get("research_brief", ""))
        return vote_from_ml_prediction(
            pred,
            round_num,
            reasoning=brief[:500] if brief else str(pred.get("ml_summary", "")),
        )

    raw = str(result.get("research_brief", ""))
    fallback = parse_vote(raw, "research_specialist", round_num)
    research_ml_log(
        "research fallback parse_vote",
        payload={"probability": fallback.probability, "key_signal": fallback.key_signal},
    )
    return fallback


@weave.op()
def run_research_specialist(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str = "",
    round: int = 1,
    model: str | None = None,
    group: str = "",
) -> AgentVote:
    _ = model or settings.wandb_research_model
    research_ml_log(
        f"run_research_specialist start round={round} {team_a} vs {team_b}"
    )
    ensure_model()
    state = _initial_state(match_query, team_a, team_b, context, round, group)
    result = compiled_research_graph.invoke(state)
    vote = _resolve_research_vote(state, result)

    research_ml_log(
        "run_research_specialist done",
        payload={
            "probability": vote.probability,
            "score": f"{vote.team_a_goals}-{vote.team_b_goals}",
            "key_signal": vote.key_signal[:120],
        },
    )
    return vote


@weave.op()
async def run_research_specialist_async(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str = "",
    round: int = 1,
    model: str | None = None,
    group: str = "",
) -> AgentVote:
    return await asyncio.to_thread(
        run_research_specialist,
        match_query,
        team_a,
        team_b,
        context,
        round,
        model,
        group,
    )
