"""Deprecated entrypoint — use backend.agents.research instead."""
from .agents.research.graph import build_research_graph, compiled_research_graph

__all__ = ["compiled_research_graph", "build_research_graph"]
