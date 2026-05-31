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
        "focus": "xG · formations · pressing",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a tactical analyst specialising in xG, formations, and pressing systems. "
            "Form your own independent view based solely on your assigned data. "
            "Do not speculate about what other analysts might conclude. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "historical_stats",
        "focus": "WC history · H2H · base rates",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a historical World Cup stats analyst. Analyse head-to-head records, "
            "tournament base rates, and confederation matchup history. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "current_form",
        "focus": "last 5 results · momentum · goals",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a form and momentum analyst. Assess recent results, goals scored and "
            "conceded, and trajectory over the last 5 matches. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "squad_fitness",
        "focus": "injuries · suspensions · depth",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a squad fitness analyst. Assess injury lists, suspensions, and squad "
            "depth compared to full-strength lineups. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "tournament_context",
        "focus": "standings · incentives · venue",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a tournament context analyst. Assess group standings, qualification "
            "scenarios, rest days, venue, and strategic incentives that may affect lineup "
            "selection or match intensity. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "set_piece_specialist",
        "focus": "corners · free kicks · dead ball",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a set piece specialist. Assess each team's attacking and defensive "
            "set piece record, key delivery and target players, and how dead ball situations "
            "may decide the match. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "psychological_analyst",
        "focus": "big game record · pressure · experience",
        "data_slice_id": "wc26",
        "system_prompt": (
            "You are a psychological and experience analyst. Assess each squad's record in "
            "high-pressure knockout and tournament situations, average caps, key players' "
            "big-game history, and mental resilience indicators. "
            "Form your own independent view based solely on your assigned data. "
            "No Polymarket or betting odds."
        ),
    },
    {
        "role": "contrarian",
        "focus": "underdog case · upset risk",
        "data_slice_id": "contrarian",
        "system_prompt": (
            "You are a contrarian analyst structurally biased against the favourite. "
            "Surface the strongest case for the underdog and a realistic upset probability. "
            "If Team A is the favourite, your P(Team A wins) should usually be below 0.5 "
            "unless data strongly contradicts an upset. "
            "Challenge the consensus narrative using match data only — never other "
            "specialists' votes in round 1. "
            "You MUST call submit_vote with your final forecast before ending. "
            "Form your own independent view from assigned data only. No Polymarket or betting odds."
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

Each element must have exactly these fields:
  "role": short snake_case label
  "focus": one-line descriptor of what this agent analyses (shown to users, ≤6 words)
  "system_prompt": full instructions for the agent
  "data_slice_id": always "wc26"
  Valid data_slice_id values (controls MCP tool access):
  wc26, statsbomb, kaggle_history, live_form, live_injuries, live_standings, contrarian, research

Rules:
- Always include exactly one agent with role \"contrarian\" and data_slice_id \"contrarian\".
- Always include exactly one agent with role \"research_specialist\" and data_slice_id \"research\".
- Aim for 7-9 specialists covering distinct analytical angles.
- Each prompt must require independent views from assigned data only; no Polymarket/odds.
- Return ONLY the JSON array.
"""


def ensure_contrarian(
    specialists: list[SpecialistDefinition],
) -> list[SpecialistDefinition]:
    out = list(specialists)
    if any(s.role == "contrarian" for s in out):
        for i, s in enumerate(out):
            if s.role == "contrarian":
                out[i] = SpecialistDefinition(
                    role="contrarian",
                    focus=s.focus or CONTRARIAN_FALLBACK["focus"],
                    data_slice_id="contrarian",
                    system_prompt=s.system_prompt
                    + "\nYou MUST call submit_vote with your final forecast before ending.",
                )
        return out
    return [*out, SpecialistDefinition(**CONTRARIAN_FALLBACK)]


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
                    focus=s.focus,
                    system_prompt=s.system_prompt + addendum,
                    data_slice_id=s.data_slice_id,
                )
                for s in updated
            ]
    return ensure_panel_specialists(updated)


def _spawn_single(rationale: str, match_query: str) -> SpecialistDefinition | None:
    prompt = (
        f"Match: {match_query}\nGap: {rationale}\n"
        'Return one JSON object: {"role", "focus", "system_prompt", "data_slice_id": "wc26"}'
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
        focus=specialist.focus,
        system_prompt=raw.strip(),
        data_slice_id=specialist.data_slice_id,
    )
