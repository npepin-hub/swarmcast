"""Specialist agents — parallel votes via W&B Inference."""
from __future__ import annotations

import asyncio

import weave

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON, extract_json_object, inference_chat


def _parse_vote(text: str, role: str, round: int) -> AgentVote:
    data = extract_json_object(text)
    if not data:
        return AgentVote(
            role=role,
            probability=0.5,
            confidence=0.5,
            key_signal="parse_error",
            reasoning=text[:200],
            uncertainty_flag=True,
            round=round,
        )
    return AgentVote(
        role=role,
        probability=float(data["probability"]),
        confidence=float(data["confidence"]),
        key_signal=str(data.get("key_signal", "")),
        reasoning=str(data.get("reasoning", "")),
        uncertainty_flag=bool(data.get("uncertainty_flag", False)),
        round=round,
    )


def _vote_user_message(
    match_query: str, team_a: str, team_b: str, context: str, round: int
) -> str:
    parts = [
        f"Match: {match_query}",
        f"Team A = {team_a}, Team B = {team_b}.",
        f"Round {round} vote — independent estimate.",
        VOTE_JSON,
    ]
    if context.strip():
        parts.insert(2, f"Assigned data:\n{context}")
    return "\n\n".join(parts)


@weave.op()
def run_specialist(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int = 1,
    model: str | None = None,
) -> AgentVote:
    model = model or settings.wandb_specialist_model
    raw = inference_chat(
        specialist.system_prompt,
        _vote_user_message(match_query, team_a, team_b, context, round),
        model,
    )
    return _parse_vote(raw, specialist.role, round)


@weave.op()
async def run_swarm(
    specialists: list[SpecialistDefinition],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    round: int = 1,
    model: str | None = None,
) -> list[AgentVote]:
    default_ctx = "\n\n".join(contexts.values()) if contexts else ""
    model = model or settings.wandb_specialist_model

    async def _one(spec: SpecialistDefinition) -> AgentVote:
        ctx = contexts.get(spec.data_slice_id, default_ctx)
        return await asyncio.to_thread(
            run_specialist, spec, match_query, team_a, team_b, ctx, round, model
        )

    return list(await asyncio.gather(*[_one(s) for s in specialists]))
