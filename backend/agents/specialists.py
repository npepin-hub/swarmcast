"""Specialist agents — parallel votes via W&B Inference (+ MCP tools)."""
from __future__ import annotations

import asyncio

import weave

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON, inference_chat
from .specialist_react import run_specialist_with_mcp, run_specialist_with_mcp_async
from .vote_parse import is_parse_error, parse_vote


def model_for_specialist(spec: SpecialistDefinition, default_model: str) -> str:
    if spec.role == "contrarian":
        return settings.wandb_contrarian_model
    return default_model


def _vote_user_message(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int,
    *,
    isolated: bool = False,
) -> str:
    parts = [
        f"Match: {match_query}",
        f"Team A = {team_a}, Team B = {team_b}.",
        f"Round {round} vote — predict the final score (goals for each team) and P(team A wins).",
        VOTE_JSON,
    ]
    if isolated:
        parts.insert(
            2,
            "Round 1: vote independently. Do not reference other analysts or panel votes.",
        )
    if context.strip():
        parts.insert(2 if not isolated else 3, f"Assigned data:\n{context}")
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
    *,
    isolated: bool = False,
) -> AgentVote:
    """Single-shot vote using pre-loaded context only (no MCP tool loop)."""
    model = model or settings.wandb_specialist_model
    raw = inference_chat(
        specialist.system_prompt,
        _vote_user_message(
            match_query, team_a, team_b, context, round, isolated=isolated
        ),
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
    *,
    isolated: bool = False,
) -> AgentVote:
    model = model or model_for_specialist(specialist, settings.wandb_specialist_model)
    if settings.specialist_use_mcp_tools:
        return run_specialist_with_mcp(
            specialist,
            match_query,
            team_a,
            team_b,
            context,
            round,
            group,
            model,
            isolated=isolated,
        )
    return run_specialist_plain(
        specialist,
        match_query,
        team_a,
        team_b,
        context,
        round,
        model,
        isolated=isolated,
    )


async def _run_one_specialist(
    spec: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    default_ctx: str,
    round: int,
    group: str,
    model: str,
    *,
    isolated: bool,
) -> AgentVote:
    ctx = contexts.get(spec.data_slice_id, default_ctx)
    vote: AgentVote | None = None
    attempts = 1 + settings.vote_parse_retries
    for attempt in range(attempts):
        if settings.specialist_use_mcp_tools:
            vote = await run_specialist_with_mcp_async(
                spec,
                match_query,
                team_a,
                team_b,
                ctx,
                round,
                group,
                model,
                isolated=isolated,
            )
        else:
            vote = await asyncio.to_thread(
                run_specialist_plain,
                spec,
                match_query,
                team_a,
                team_b,
                ctx,
                round,
                model,
                isolated=isolated,
            )
        if not is_parse_error(vote):
            return vote
        if attempt < attempts - 1:
            ctx = (
                f"{ctx}\n\n[RETRY] Your previous response was not valid JSON. "
                "Call submit_vote or return ONLY the vote JSON."
            )
    return vote  # type: ignore[return-value]


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
    *,
    isolated: bool = False,
) -> list[AgentVote]:
    default_ctx = "\n\n".join(contexts.values()) if contexts else ""
    model = model or settings.wandb_specialist_model

    tasks = [
        _run_one_specialist(
            spec,
            match_query,
            team_a,
            team_b,
            contexts,
            default_ctx,
            round,
            group,
            model_for_specialist(spec, model),
            isolated=isolated,
        )
        for spec in specialists
    ]
    return list(await asyncio.gather(*tasks))
