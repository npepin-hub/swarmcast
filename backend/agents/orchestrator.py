"""Meta-orchestrator — spawn / rewrite / broadcast via W&B Inference."""
from __future__ import annotations

import json

import weave

from ..config import settings
from ..schemas import CritiqueOutput, CriticAction, RecommendedAction, SpecialistDefinition
from .inference import extract_json_array, extract_json_object, inference_chat

FALLBACK_SPECIALISTS: list[dict] = [
    {
        "role": "tactical_analyst",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a tactical analyst (xG, formations, pressing). "
            "Form your own independent view based solely on your assigned data. "
            "Do not speculate about what other analysts might conclude. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "historical_stats",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a historical World Cup stats analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "current_form",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a form and momentum analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "squad_fitness",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a squad fitness and injuries analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "tournament_context",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a tournament context analyst (standings, incentives). "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "contrarian",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a contrarian analyst biased against the favourite. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
]

_SPAWN_SYSTEM = """\
You are a meta-orchestrator for a multi-agent sports forecasting system.
Given a match question, return a JSON array of specialist definitions.
Each element: {"role": str, "system_prompt": str, "data_slice_id": "wc26"}
Rules:
- Always include a contrarian agent.
- Each prompt must require independent views from assigned data only; no Polymarket/odds.
- Return ONLY the JSON array.
"""


@weave.op()
def spawn_specialists(match_query: str, team_a: str = "", team_b: str = "") -> list[SpecialistDefinition]:
    user = match_query
    if team_a and team_b:
        user = f"{match_query}\nTeam A: {team_a}, Team B: {team_b}"
    raw = inference_chat(_SPAWN_SYSTEM, user, settings.wandb_orchestrator_model)
    arr = extract_json_array(raw)
    if arr:
        try:
            return [SpecialistDefinition(**d) for d in arr]
        except Exception:
            pass
    try:
        definitions = json.loads(raw)
        return [SpecialistDefinition(**d) for d in definitions]
    except Exception:
        return [SpecialistDefinition(**s) for s in FALLBACK_SPECIALISTS]


@weave.op()
def act_on_critique(
    critique: CritiqueOutput,
    specialists: list[SpecialistDefinition],
    match_query: str,
) -> list[SpecialistDefinition]:
    updated = list(specialists)
    for rec in critique.recommended_actions:
        if rec.action == CriticAction.spawn:
            new_def = _spawn_single(rec.rationale, match_query)
            if new_def:
                updated.append(new_def)
        elif rec.action == CriticAction.rewrite and rec.target_role:
            for i, s in enumerate(updated):
                if s.role == rec.target_role:
                    updated[i] = _rewrite_prompt(s, rec.rationale, match_query)
        elif rec.action == CriticAction.broadcast:
            addendum = f"\n\n[CRITIC ADDENDUM] {rec.rationale}"
            updated = [
                SpecialistDefinition(
                    role=s.role,
                    system_prompt=s.system_prompt + addendum,
                    data_slice_id=s.data_slice_id,
                )
                for s in updated
            ]
    return updated


def _spawn_single(rationale: str, match_query: str) -> SpecialistDefinition | None:
    prompt = (
        f"Match: {match_query}\nGap: {rationale}\n"
        'Return one JSON object: {"role", "system_prompt", "data_slice_id": "wc26"}'
    )
    raw = inference_chat(_SPAWN_SYSTEM, prompt, settings.wandb_orchestrator_model)
    data = extract_json_object(raw)
    if data:
        try:
            return SpecialistDefinition(**data)
        except Exception:
            return None
    return None


def _rewrite_prompt(
    specialist: SpecialistDefinition, rationale: str, match_query: str
) -> SpecialistDefinition:
    prompt = (
        f"Rewrite system prompt for '{specialist.role}'.\n"
        f"Critic: {rationale}\nOriginal:\n{specialist.system_prompt}\n"
        "Return only the new prompt text."
    )
    raw = inference_chat(
        "You rewrite agent prompts to fix groupthink.",
        prompt,
        settings.wandb_orchestrator_model,
    )
    return SpecialistDefinition(
        role=specialist.role,
        system_prompt=raw.strip(),
        data_slice_id=specialist.data_slice_id,
    )
