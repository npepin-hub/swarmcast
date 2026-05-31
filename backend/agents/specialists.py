"""Specialist agents — parallel votes via W&B Inference (+ MCP tools)."""
from __future__ import annotations

import asyncio

import weave

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON, inference_chat
from .specialist_react import run_specialist_with_mcp_async
from .vote_parse import parse_vote


def _vote_user_message(
    match_query: str, team_a: str, team_b: str, context: str, round: int
) -> str:
    parts = [
        f"Match: {match_query}",
        f"Team A = {team_a}, Team B = {team_b}.",
        f"Round {round} vote — predict the final score (goals for each team) and P(team A wins).",
        VOTE_JSON,
    ]
    if context.strip():
        parts.insert(2, f"Assigned data:\n{context}")
    return "\n\n".join(parts)


@weave.op()
def run_specialist_plain(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int = 1,
    model: str | None = None,
) -> AgentVote:
    """Single-shot vote using pre-loaded context only (no MCP tool loop)."""
    model = model or settings.wandb_specialist_model
    raw = inference_chat(
        specialist.system_prompt,
        _vote_user_message(match_query, team_a, team_b, context, round),
        model,
    )
    return parse_vote(raw, specialist.role, round)


@weave.op()
def run_specialist(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int = 1,
    group: str = "",
    model: str | None = None,
) -> AgentVote:
    if settings.specialist_use_mcp_tools:
        return run_specialist_with_mcp(
            specialist, match_query, team_a, team_b, context, round, group, model
        )
    return run_specialist_plain(
        specialist, match_query, team_a, team_b, context, round, model
    )


@weave.op()
async def run_swarm(
    specialists: list[SpecialistDefinition],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    round: int = 1,
    group: str = "",
    model: str | None = None,
) -> list[AgentVote]:
    default_ctx = "\n\n".join(contexts.values()) if contexts else ""
    model = model or settings.wandb_specialist_model

    async def _one(spec: SpecialistDefinition) -> AgentVote:
        ctx = contexts.get(spec.data_slice_id, default_ctx)
        if settings.specialist_use_mcp_tools:
            return await run_specialist_with_mcp_async(
                spec, match_query, team_a, team_b, ctx, round, group, model
            )
        return await asyncio.to_thread(
            run_specialist_plain,
            spec,
            match_query,
            team_a,
            team_b,
            ctx,
            round,
            model,
        )

    return list(await asyncio.gather(*[_one(s) for s in specialists]))
