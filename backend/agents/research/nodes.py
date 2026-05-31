"""LangGraph nodes: Researcher → ModelBaseline → Synthesizer → Auditor → Vote."""
from __future__ import annotations

import json
import logging
from typing import Any

from ...config import settings
from ...schemas import AgentVote
from .ml_log import research_ml_log

logger = logging.getLogger(__name__)
from ..inference import VOTE_JSON
from ..vote_parse import ROUND1_ISOLATION, parse_vote
from .knowledge_graph import KnowledgeGraph
from .mcp_features import build_match_features
from .react import extract_json_object, run_react_agent
from .state import ResearchState
from .wc_model import ensure_model, predict_match


def _isolation_block(round_num: int) -> str:
    if round_num == 1:
        return ROUND1_ISOLATION
    return (
        "\nROUND 2: You may use the Delphi aggregate in context. "
        "You have NOT seen other agents' individual round-1 votes.\n"
    )


def _ml_baseline_block(pred: dict) -> str:
    if not pred:
        return ""
    ta, tb = pred.get("team_a"), pred.get("team_b")
    return (
        f"\nML baseline (sklearn + form blend on MCP/CSV features):\n"
        f"- {pred.get('ml_summary', '')}\n"
        f"- Blended P({ta} wins) = {pred.get('probability_team_a', 0.5):.3f} "
        f"(tournament-only={pred.get('probability_team_a_tournament', 0.5):.3f}, "
        f"form-only={pred.get('probability_team_a_features', 0.5):.3f})\n"
        f"- Suggested score: {pred.get('team_a_goals')}-{pred.get('team_b_goals')}\n"
        f"- Tournament model favors: {pred.get('model_favored_team')}; "
        f"raw form favors: {pred.get('form_favored_team')}\n"
    )


def researcher_node(state: ResearchState) -> dict[str, Any]:
    question = state.get("match_query", "")
    team_a = state.get("team_a", "")
    team_b = state.get("team_b", "")
    context = state.get("context", "")
    round_num = state.get("round", 1)

    instruction = f"""{_isolation_block(round_num)}
You are the Researcher for a World Cup match forecast.

Match question: {question}
Team A = {team_a}, Team B = {team_b}

Pre-loaded context (may be partial):
{context or "(none)"}

Task:
1. Extract football entities (teams, form, injuries, H2H, venue, tactics).
2. Build semantic triples: [subject, predicate, object].
3. Rephrase the question for analysis.

Final Answer MUST be raw JSON only:
{{
  "rephrased_question": "<text>",
  "triples": [["subject", "predicate", "object"], ...]
}}
"""
    respond = run_react_agent(instruction)
    data = extract_json_object(respond) or {}

    rephrased = data.get("rephrased_question", question)
    triples = data.get("triples", [])
    if not isinstance(triples, list):
        triples = []
    kg = KnowledgeGraph(triples if triples else [[team_a, "plays", team_b]])

    return {
        "rephrased_question": rephrased,
        "knowledge_graph": kg,
        "audit_status": "RESEARCH-DONE",
        "history": state.get("history", []) + ["Researcher"],
    }


def model_baseline_node(state: ResearchState) -> dict[str, Any]:
    """Fetch MCP features, run model.pkl, store baseline for hybrid vote."""
    team_a = state.get("team_a", "")
    team_b = state.get("team_b", "")
    use_mcp = settings.research_use_mcp_features

    try:
        ensure_model()
        research_ml_log(
            f"ModelBaseline team_a={team_a} team_b={team_b} use_mcp={use_mcp}"
        )
        feature_df, provenance = build_match_features(team_a, team_b, use_mcp=use_mcp)
        research_ml_log(
            "features built",
            payload={
                "rows": feature_df.to_dict(orient="records"),
                "provenance": provenance,
            },
        )
        prediction = predict_match(team_a, team_b, feature_df)
        return {
            "model_features": {
                "provenance": provenance,
                "rows": feature_df.to_dict(orient="records"),
            },
            "model_prediction": prediction,
            "history": state.get("history", []) + ["ModelBaseline"],
        }
    except Exception as exc:
        research_ml_log(f"ModelBaseline failed: {exc}")
        logger.exception("[research-ml] ModelBaseline failed: %s", exc)
        return {
            "model_features": {"error": str(exc)},
            "model_prediction": {},
            "history": state.get("history", []) + ["ModelBaseline:error"],
        }


def synthesizer_node(state: ResearchState) -> dict[str, Any]:
    kg = state.get("knowledge_graph")
    kg_text = kg.summary() if isinstance(kg, KnowledgeGraph) else str(kg)
    round_num = state.get("round", 1)
    pred = state.get("model_prediction") or {}
    ml_block = _ml_baseline_block(pred)
    ml_note = pred.get("ml_summary", "")

    instruction = f"""{_isolation_block(round_num)}
You are the Synthesizer for match research.

Question: {state.get("rephrased_question") or state.get("match_query")}
Team A = {state.get("team_a")}, Team B = {state.get("team_b")}
{ml_block}

Knowledge graph:
{kg_text}

Task: Produce a research brief as JSON (no betting odds, no Polymarket).
Incorporate the ML baseline as one factor; explain agreement or tension with KG.
ML context: {ml_note or "(none)"}

Final Answer MUST be raw JSON:
{{
  "key_factors": ["<factor 1>", "<factor 2>", "..."],
  "risks": ["..."],
  "favourite": "<team or undecided>",
  "underdog_case": "<one paragraph>",
  "ml_baseline_note": "<how ML baseline relates to football factors>",
  "summary": "<2-3 sentences for Reasoning panel>"
}}
"""
    respond = run_react_agent(instruction)
    data = extract_json_object(respond) or {}
    brief = data if data else {"summary": respond[:500]}

    return {
        "research_brief": json.dumps(brief, indent=2),
        "audit_status": "DRAFT-DONE",
        "history": state.get("history", []) + ["Synthesizer"],
    }


def auditor_node(state: ResearchState) -> dict[str, Any]:
    round_num = state.get("round", 1)
    instruction = f"""{_isolation_block(round_num)}
You are the Compliance Auditor for SwarmCast research.

Research brief:
{state.get("research_brief", "")}

Rules:
- No betting odds or Polymarket prices referenced.
- Round 1: must not reference other specialists' votes.
- Brief must support a football match forecast.

End with exactly one line: STATUS: COMPLETE or STATUS: REVISION-REQUIRED
"""
    respond = run_react_agent(instruction)
    status = (
        "COMPLETE"
        if "STATUS: COMPLETE" in respond.upper()
        else "REVISION-REQUIRED"
    )
    rev = state.get("revision_count", 0)
    if status == "REVISION-REQUIRED":
        rev += 1
    return {
        "audit_status": status,
        "revision_count": rev,
        "history": state.get("history", []) + ["Auditor"],
    }


def _looks_like_json(text: str) -> bool:
    t = (text or "").strip()
    return t.startswith("{") or t.startswith("[")


def _format_brief_reasoning(brief_str: str) -> str:
    """Turn synthesizer JSON brief into readable prose (never raw JSON in UI)."""
    data = extract_json_object(brief_str) if brief_str else None
    if not data:
        if _looks_like_json(brief_str):
            return "Research brief could not be parsed; see Weave trace for full output."
        return (brief_str or "").strip()[:500]

    blocks: list[str] = []
    summary = str(data.get("summary", "")).strip()
    if summary:
        blocks.append(summary)
    ml_note = str(data.get("ml_baseline_note", "")).strip()
    if ml_note:
        blocks.append(ml_note)
    factors = data.get("key_factors") or []
    if isinstance(factors, list) and factors:
        bullets = "; ".join(str(f).strip() for f in factors[:4] if f)
        if bullets:
            blocks.append(f"Key factors: {bullets}")
    risks = data.get("risks") or []
    if isinstance(risks, list) and risks:
        blocks.append("Risks: " + "; ".join(str(r).strip() for r in risks[:3] if r))
    underdog = str(data.get("underdog_case", "")).strip()
    if underdog:
        blocks.append(underdog)
    fav = str(data.get("favourite", "")).strip()
    if fav and fav.lower() not in summary.lower():
        blocks.append(f"Favourite: {fav}")
    return "\n\n".join(blocks)[:800]


def _brief_top_factor(brief_str: str) -> str:
    data = extract_json_object(brief_str) if brief_str else None
    if not data:
        return ""
    factors = data.get("key_factors") or []
    if isinstance(factors, list) and factors:
        return str(factors[0]).strip()[:120]
    return str(data.get("summary", "")).strip()[:120]


def _compact_ml_signal(pred: dict, team_a: str, team_b: str) -> str:
    """One-line Signal for the aggregate table."""
    if not pred:
        return ""
    pa = float(pred.get("probability_team_a", 0.5))
    pt = pred.get("probability_team_a_tournament")
    pf = pred.get("probability_team_a_features")
    ga = pred.get("team_a_goals", 1)
    gb = pred.get("team_b_goals", 1)
    form_f = pred.get("form_favored_team", "")
    model_f = pred.get("model_favored_team", "")
    parts = [f"P({team_a})={pa:.0%}", f"score {ga}-{gb}"]
    if pf is not None:
        parts.append(f"form→{form_f} ({float(pf):.0%})")
    if pt is not None:
        parts.append(f"WC-model→{model_f} ({float(pt):.0%})")
    return " · ".join(parts)


def _is_redundant_signal(text: str) -> bool:
    t = (text or "").strip()
    if not t or t == "parse_error":
        return True
    if _looks_like_json(t):
        return True
    return "Form (" in t and "weight)" in t and len(t) > 120


def _enrich_research_vote(
    state: ResearchState,
    vote: AgentVote,
) -> AgentVote:
    """Ensure key_signal and reasoning are populated for UI Signal / Reasoning rows."""
    team_a = state.get("team_a", "Team A")
    team_b = state.get("team_b", "Team B")
    pred = state.get("model_prediction") or {}
    brief = state.get("research_brief", "") or ""

    key_signal = _compact_ml_signal(pred, team_a, team_b)
    factor = _brief_top_factor(brief)
    if factor and factor not in key_signal:
        key_signal = f"{key_signal} — {factor}" if key_signal else factor
    key_signal = (key_signal or f"Research forecast {team_a} vs {team_b}")[:240]

    reasoning = _format_brief_reasoning(brief)
    llm_reason = (vote.reasoning or "").strip()
    if (
        llm_reason
        and llm_reason != "parse_error"
        and not _looks_like_json(llm_reason)
        and llm_reason not in reasoning
    ):
        reasoning = f"{reasoning}\n\n{llm_reason}" if reasoning else llm_reason

    if not reasoning:
        reasoning = str(pred.get("ml_summary", ""))[:500] or key_signal

    return vote.model_copy(
        update={
            "key_signal": key_signal,
            "reasoning": reasoning[:800],
        }
    )


def _clamp_vote_to_baseline(vote: AgentVote, pred: dict) -> AgentVote:
    clamp = settings.research_ml_vote_clamp
    if clamp <= 0 or not pred:
        return vote
    baseline_p = float(pred.get("probability_team_a", 0.5))
    low = max(0.0, baseline_p - clamp)
    high = min(1.0, baseline_p + clamp)
    p = max(low, min(high, vote.probability))
    return vote.model_copy(update={"probability": p})


def vote_from_ml_prediction(
    pred: dict,
    round_num: int,
    *,
    key_signal: str = "",
    reasoning: str = "",
) -> AgentVote:
    """Build AgentVote from predict_match output (used when Vote node did not run)."""
    team_a = str(pred.get("team_a", "Team A"))
    team_b = str(pred.get("team_b", "Team B"))
    return AgentVote(
        role="research_specialist",
        team_a_goals=int(pred.get("team_a_goals", 1)),
        team_b_goals=int(pred.get("team_b_goals", 1)),
        probability=float(pred.get("probability_team_a", 0.5)),
        confidence=0.75,
        key_signal="",
        reasoning="",
        uncertainty_flag=False,
        round=round_num,
    )


def _finalize_research_vote(
    state: ResearchState,
    vote: AgentVote,
    pred: dict,
) -> AgentVote:
    """Match vote always uses ML baseline P and score; LLM supplies narrative only."""
    if not pred:
        return _enrich_research_vote(state, vote)

    baseline_p = float(pred.get("probability_team_a", 0.5))
    goals_a = int(pred.get("team_a_goals", vote.team_a_goals))
    goals_b = int(pred.get("team_b_goals", vote.team_b_goals))
    llm_p = vote.probability

    if abs(llm_p - baseline_p) > 0.02:
        research_ml_log(
            "vote probability set from ML baseline",
            payload={
                "llm_probability": llm_p,
                "baseline_probability": baseline_p,
                "parse_error": vote.key_signal == "parse_error",
            },
        )

    vote = vote.model_copy(
        update={
            "probability": baseline_p,
            "team_a_goals": goals_a,
            "team_b_goals": goals_b,
            "confidence": max(vote.confidence, 0.7),
            "uncertainty_flag": False,
        }
    )
    return _enrich_research_vote(state, vote)


def vote_node(state: ResearchState) -> dict[str, Any]:
    kg = state.get("knowledge_graph")
    kg_text = kg.summary() if isinstance(kg, KnowledgeGraph) else str(kg)
    round_num = state.get("round", 1)
    pred = state.get("model_prediction") or {}
    ml_block = _ml_baseline_block(pred)
    clamp = settings.research_ml_vote_clamp

    instruction = f"""{_isolation_block(round_num)}
You are the research_specialist. Submit your independent match forecast.

Team A = {state.get("team_a")} (goals = team_a_goals)
Team B = {state.get("team_b")} (goals = team_b_goals)
{ml_block}

Research brief:
{state.get("research_brief", "")}

Knowledge graph:
{kg_text}

HYBRID RULE: Your "probability" should be close to the blended ML baseline ({pred.get("probability_team_a", 0.5):.1%} for {state.get("team_a")}).
Do NOT default to 0.50 unless the match is truly even. Brazil vs weaker opponents should reflect form (often 55-75% for the favourite).
If you differ, stay within ±{clamp:.2f} of the ML baseline.
Suggested goals from ML: {pred.get("team_a_goals", 1)}-{pred.get("team_b_goals", 1)}.

Panel / Delphi context (round {round_num}):
{state.get("context", "")[:1200]}

{VOTE_JSON}

You MUST include non-empty "key_signal" (one line) and "reasoning" (2-4 sentences citing ML baseline + brief).

Final Answer: ONLY the vote JSON object.
"""
    respond = run_react_agent(instruction, max_loops=2)
    vote = parse_vote(respond, "research_specialist", round_num)
    vote = _finalize_research_vote(state, vote, pred)

    return {
        "vote": vote,
        "audit_status": "VOTE-DONE",
        "history": state.get("history", []) + ["Vote"],
    }
