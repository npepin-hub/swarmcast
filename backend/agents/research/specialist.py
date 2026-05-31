"""Research specialist — LangGraph pipeline → AgentVote."""
from __future__ import annotations

import asyncio

import weave

from ...config import settings
from ...schemas import AgentVote
from ..vote_parse import parse_vote
from .graph import compiled_research_graph
from .state import ResearchState


def _initial_state(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int,
) -> ResearchState:
    return ResearchState(
        match_query=match_query,
        team_a=team_a,
        team_b=team_b,
        context=context,
        round=round,
        rephrased_question=match_query,
        research_brief="",
        audit_status="",
        revision_count=0,
        history=[],
    )


@weave.op()
def run_research_specialist(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str = "",
    round: int = 1,
    model: str | None = None,
) -> AgentVote:
    _ = model or settings.wandb_research_model
    state = _initial_state(match_query, team_a, team_b, context, round)
    result = compiled_research_graph.invoke(state)

    vote = result.get("vote")
    if isinstance(vote, AgentVote):
        return vote

    raw = ""
    if isinstance(result.get("research_brief"), str):
        raw = result["research_brief"]
    return parse_vote(raw, "research_specialist", round)


@weave.op()
async def run_research_specialist_async(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str = "",
    round: int = 1,
    model: str | None = None,
) -> AgentVote:
    return await asyncio.to_thread(
        run_research_specialist,
        match_query,
        team_a,
        team_b,
        context,
        round,
        model,
    )
