"""Compiled LangGraph for the research specialist."""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from .nodes import (
    auditor_node,
    model_baseline_node,
    researcher_node,
    synthesizer_node,
    vote_node,
)
from .state import ResearchState


def _route_after_research(state: ResearchState) -> str:
    if state.get("audit_status") == "RESEARCH-DONE":
        return "ModelBaseline"
    return END


def _route_after_model(state: ResearchState) -> str:
    return "Synthesizer"


def _route_after_synth(state: ResearchState) -> str:
    if state.get("audit_status") == "DRAFT-DONE":
        return "Auditor"
    return END


def _route_after_audit(state: ResearchState) -> str:
    status = state.get("audit_status", "")
    revisions = state.get("revision_count", 0)
    if status == "REVISION-REQUIRED" and revisions < 1:
        return "Synthesizer"
    if status in ("COMPLETE", "REVISION-REQUIRED"):
        return "Vote"
    return END


def build_research_graph():
    workflow = StateGraph(ResearchState)
    workflow.add_node("Researcher", researcher_node)
    workflow.add_node("ModelBaseline", model_baseline_node)
    workflow.add_node("Synthesizer", synthesizer_node)
    workflow.add_node("Auditor", auditor_node)
    workflow.add_node("Vote", vote_node)

    workflow.set_entry_point("Researcher")
    workflow.add_conditional_edges(
        "Researcher", _route_after_research, {"ModelBaseline": "ModelBaseline", END: END}
    )
    workflow.add_conditional_edges(
        "ModelBaseline", _route_after_model, {"Synthesizer": "Synthesizer", END: END}
    )
    workflow.add_conditional_edges(
        "Synthesizer", _route_after_synth, {"Auditor": "Auditor", END: END}
    )
    workflow.add_conditional_edges(
        "Auditor",
        _route_after_audit,
        {"Synthesizer": "Synthesizer", "Vote": "Vote", END: END},
    )
    workflow.add_edge("Vote", END)
    return workflow.compile()


compiled_research_graph = build_research_graph()
