"""LangGraph state for the research specialist."""
from __future__ import annotations

from typing import Any, TypedDict

from .knowledge_graph import KnowledgeGraph


class ResearchState(TypedDict, total=False):
    match_query: str
    team_a: str
    team_b: str
    context: str
    group: str
    round: int
    rephrased_question: str
    knowledge_graph: KnowledgeGraph | Any
    research_brief: str
    audit_status: str
    revision_count: int
    history: list[str]
    model_features: dict
    model_prediction: dict
