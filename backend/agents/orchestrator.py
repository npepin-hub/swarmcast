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
        "data_slice_id": "statsbomb",
        "system_prompt": (
            "You are a tactical analyst (xG, formations, pressing). "
            "Use MCP tools on your slice to fetch data; form an independent view. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "historical_stats",
        "data_slice_id": "kaggle_history",
        "system_prompt": (
            "You are a historical World Cup stats analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "current_form",
        "data_slice_id": "live_form",
        "system_prompt": (
            "You are a form and momentum analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "squad_fitness",
        "data_slice_id": "live_injuries",
        "system_prompt": (
            "You are a squad fitness and injuries analyst. "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "tournament_context",
        "data_slice_id": "live_standings",
        "system_prompt": (
            "You are a tournament context analyst (standings, incentives). "
            "Form your own independent view based solely on your assigned data."
        ),
    },
    {
        "role": "contrarian",
        "data_slice_id": "contrarian",
        "system_prompt": (
            "You are a contrarian analyst. Challenge the favourite / consensus "
            "narrative using match data only — never other specialists' votes. "
            "Always submit a concrete score and win probability."
        ),
    },
]

CONTRARIAN_FALLBACK = FALLBACK_SPECIALISTS[-1]

RESEARCH_FALLBACK: dict = {
    "role": "research_specialist",
    "data_slice_id": "research",
    "system_prompt": (
        "You are the research specialist. Build a knowledge graph of match factors, "
        "synthesize a brief, pass compliance, then forecast score and win probability. "
        "Never use betting odds or other specialists' votes in round 1."
    ),
}

_SPAWN_SYSTEM = """\
You are a meta-orchestrator for a multi-agent sports forecasting system.
Given a match question, return a JSON array of specialist definitions.
Each element: {"role": str, "system_prompt": str, "data_slice_id": str}
Valid data_slice_id values (controls MCP tool access):
  statsbomb, kaggle_history, live_form, live_injuries, live_standings, contrarian, research
Rules:
- Always include exactly one agent with role \"contrarian\" and data_slice_id \"contrarian\".
- Always include exactly one agent with role \"research_specialist\" and data_slice_id \"research\".
- Specialists use MCP tools on their slice; round 1 is blind — no peer votes; no Polymarket/odds.
- Return ONLY the JSON array.
"""


def ensure_contrarian(
    specialists: list[SpecialistDefinition],
) -> list[SpecialistDefinition]:
    if any(s.role == "contrarian" for s in specialists):
        return specialists
    return [*specialists, SpecialistDefinition(**CONTRARIAN_FALLBACK)]


def ensure_research_specialist(
    specialists: list[SpecialistDefinition],
) -> list[SpecialistDefinition]:
    if any(s.role == "research_specialist" for s in specialists):
        return specialists
    return [*specialists, SpecialistDefinition(**RESEARCH_FALLBACK)]


def ensure_panel_specialists(
    specialists: list[SpecialistDefinition],
) -> list[SpecialistDefinition]:
    return ensure_research_specialist(ensure_contrarian(specialists))


@weave.op()
def spawn_specialists(match_query: str, team_a: str = "", team_b: str = "") -> list[SpecialistDefinition]:
    user = match_query
    if team_a and team_b:
        user = f"{match_query}\nTeam A: {team_a}, Team B: {team_b}"
    raw = inference_chat(_SPAWN_SYSTEM, user, settings.wandb_orchestrator_model)
    arr = extract_json_array(raw)
    if arr:
        try:
            return ensure_panel_specialists([SpecialistDefinition(**d) for d in arr])
        except Exception:
            pass
    try:
        definitions = json.loads(raw)
        return ensure_panel_specialists(
            [SpecialistDefinition(**d) for d in definitions]
        )
    except Exception:
        return ensure_panel_specialists(
            [SpecialistDefinition(**s) for s in FALLBACK_SPECIALISTS]
        )


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
