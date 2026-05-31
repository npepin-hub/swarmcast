"""Specialist agents — parallel votes via W&B Inference (+ MCP tools)."""
from __future__ import annotations

import asyncio

import weave

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON, inference_chat
from .research.specialist import run_research_specialist_async
from .specialist_react import run_specialist_with_mcp_async
from .vote_parse import ROUND1_ISOLATION, is_parse_error, parse_vote


def model_for_specialist(spec: SpecialistDefinition, default_model: str) -> str:
    if spec.role == "contrarian":
        return settings.wandb_contrarian_model
    if spec.role == "research_specialist":
        return settings.wandb_research_model
    return default_model


def _vote_user_message(
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int,
    specialist: SpecialistDefinition,
    *,
    isolated: bool = False,
) -> str:
    parts = [
        f"Match: {match_query}",
        f"Team A = {team_a}, Team B = {team_b}.",
        ROUND1_ISOLATION if round == 1 or isolated else "",
        f"Round {round} vote — predict the final score (goals for each team) and P(team A wins).",
        VOTE_JSON,
    ]
    if specialist.role == "contrarian":
        parts.insert(
            3,
            "You are the contrarian: challenge the favourite using only your data — "
            "not other specialists' views.",
        )
    if isolated and round > 1:
        parts.insert(
            3,
            "Round 1 isolation: do not reference other analysts or panel votes.",
        )
    if context.strip():
        parts.insert(3, f"Assigned data:\n{context}")
    return "\n\n".join(p for p in parts if p)


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
    model = model or model_for_specialist(specialist, settings.wandb_specialist_model)
    raw = inference_chat(
        specialist.system_prompt,
        _vote_user_message(
            match_query, team_a, team_b, context, round, specialist, isolated=isolated
        ),
        model,
    )
    return parse_vote(raw, specialist.role, round)


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
    if spec.role == "research_specialist":
        print(f"[swarm] dispatch research_specialist round={round}", flush=True)
        # Include orchestrator/Delphi system_prompt (R2+ addendum) — graph only read `context` before.
        research_ctx = "\n\n".join(
            p for p in (spec.system_prompt.strip(), ctx.strip()) if p
        )
        return await run_research_specialist_async(
            match_query,
            team_a,
            team_b,
            research_ctx,
            round,
            settings.wandb_research_model,
            group,
        )

    vote: AgentVote | None = None
    attempts = 1 + settings.vote_parse_retries
    for attempt in range(attempts):
        try:
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
        except Exception as exc:
            if attempt >= attempts - 1:
                return AgentVote(
                    role=spec.role,
                    team_a_goals=0,
                    team_b_goals=0,
                    probability=0.5,
                    confidence=0.0,
                    key_signal="agent_error",
                    reasoning=str(exc)[:200],
                    uncertainty_flag=True,
                    round=round,
                )
            ctx = f"{ctx}\n\n[RETRY] Agent error: {exc}. Submit a valid vote."
            continue

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
    results = await asyncio.gather(*tasks, return_exceptions=True)
    votes: list[AgentVote] = []
    for spec, result in zip(specialists, results):
        if isinstance(result, Exception):
            print(f"[swarm] {spec.role} failed: {result}")
            votes.append(
                AgentVote(
                    role=spec.role,
                    team_a_goals=0,
                    team_b_goals=0,
                    probability=0.5,
                    confidence=0.0,
                    key_signal="agent_error",
                    reasoning=str(result)[:200],
                    uncertainty_flag=True,
                    round=round,
                )
            )
        else:
            votes.append(result)
    return votes
