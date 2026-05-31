"""Weighted consensus helpers (no LLM, stdlib only)."""
from __future__ import annotations

import math

from ..schemas import AgentVote


def weighted_consensus(votes: list[AgentVote]) -> tuple[float, float, float]:
    total_w = sum(v.confidence for v in votes) or 1.0
    mean_p = sum(v.probability * v.confidence for v in votes) / total_w
    variance = sum(v.confidence * (v.probability - mean_p) ** 2 for v in votes) / total_w
    std = math.sqrt(variance)
    ci_low = max(0.0, mean_p - 1.28 * std)
    ci_high = min(1.0, mean_p + 1.28 * std)
    return mean_p, ci_low, ci_high


def _std(votes: list[AgentVote], mean_p: float) -> float:
    if len(votes) < 2:
        return 0.0
    return math.sqrt(sum((v.probability - mean_p) ** 2 for v in votes) / len(votes))


def minority_dissent(votes: list[AgentVote], mean_p: float, std: float) -> list[AgentVote]:
    if std < 1e-6:
        return []
    return [v for v in votes if abs(v.probability - mean_p) > std]
