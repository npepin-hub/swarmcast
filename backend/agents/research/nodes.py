"""LangGraph nodes: Researcher → Synthesizer → Auditor → Vote."""
from __future__ import annotations

from typing import Any

from ..inference import VOTE_JSON
from ..vote_parse import ROUND1_ISOLATION, parse_vote
from .knowledge_graph import KnowledgeGraph
from .react import extract_json_object, run_react_agent
from .state import ResearchState


def _isolation_block(round_num: int) -> str:
    if round_num == 1:
        return ROUND1_ISOLATION
    return (
        "\nROUND 2: You may use the Delphi aggregate in context. "
        "You have NOT seen other agents' individual round-1 votes.\n"
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


def synthesizer_node(state: ResearchState) -> dict[str, Any]:
    kg = state.get("knowledge_graph")
    kg_text = kg.summary() if isinstance(kg, KnowledgeGraph) else str(kg)
    round_num = state.get("round", 1)

    instruction = f"""{_isolation_block(round_num)}
You are the Synthesizer for match research.

Question: {state.get("rephrased_question") or state.get("match_query")}
Team A = {state.get("team_a")}, Team B = {state.get("team_b")}

Knowledge graph:
{kg_text}

Task: Produce a research brief as JSON (no betting odds, no Polymarket).

Final Answer MUST be raw JSON:
{{
  "key_factors": ["..."],
  "risks": ["..."],
  "favourite": "<team or undecided>",
  "underdog_case": "<one paragraph>",
  "summary": "<2-3 sentences>"
}}
"""
    respond = run_react_agent(instruction)
    data = extract_json_object(respond) or {}
    brief = data if data else {"summary": respond[:500]}

    import json

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


def vote_node(state: ResearchState) -> dict[str, Any]:
    kg = state.get("knowledge_graph")
    kg_text = kg.summary() if isinstance(kg, KnowledgeGraph) else str(kg)
    round_num = state.get("round", 1)

    instruction = f"""{_isolation_block(round_num)}
You are the research_specialist. Submit your independent match forecast.

Team A = {state.get("team_a")} (goals = team_a_goals)
Team B = {state.get("team_b")} (goals = team_b_goals)

Research brief:
{state.get("research_brief", "")}

Knowledge graph:
{kg_text}

{VOTE_JSON}

Final Answer: ONLY the vote JSON object.
"""
    respond = run_react_agent(instruction, max_loops=2)
    vote = parse_vote(respond, "research_specialist", round_num)

    return {
        "vote": vote,
        "audit_status": "VOTE-DONE",
        "history": state.get("history", []) + ["Vote"],
    }
