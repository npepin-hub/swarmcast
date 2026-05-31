"""Semantic knowledge graph from research triples."""
from __future__ import annotations


class KnowledgeGraph:
    def __init__(self, triples: list[list[str]] | None = None):
        self.graph: dict[str, list[str]] = {}
        if triples:
            self._load_triples(triples)

    def _load_triples(self, triples: list[list[str]]) -> None:
        for row in triples:
            if len(row) < 3:
                continue
            subj, pred, obj = row[0].strip(), row[1].strip(), row[2].strip()
            self._add_edge(subj, pred, obj)
            self._add_edge(obj, f"is_{pred}_of", subj)

    def _add_edge(self, node1: str, relation: str, node2: str) -> None:
        key = node1.lower()
        if key not in self.graph:
            self.graph[key] = []
        self.graph[key].append(
            f"({node1.lower()}) -[{relation.lower()}]-> ({node2.lower()})"
        )

    def search_node(self, entity: str) -> str:
        entity_lower = entity.lower().strip()
        if entity_lower in self.graph:
            return "\n".join(self.graph[entity_lower])
        return f"No records found for entity: '{entity}'"

    def summary(self, limit: int = 40) -> str:
        edges: list[str] = []
        for edge_list in self.graph.values():
            edges.extend(edge_list)
        return "\n".join(edges[:limit]) if edges else "(empty graph)"
