"""Delphi aggregation + round 2 (LangGraph Swarm or parallel W&B)."""
from __future__ import annotations

import weave

from ..config import settings
from ..schemas import AgentVote, ConsensusResult, SpecialistDefinition
from .consensus import minority_dissent, weighted_consensus, weighted_score_consensus, _std
from .specialists import run_swarm
from .swarm_langgraph import run_delphi_langgraph


@weave.op()
def aggregate(votes: list[AgentVote]) -> ConsensusResult:
    mean_p, ci_low, ci_high = weighted_consensus(votes)
    goals_a, goals_b = weighted_score_consensus(votes)
    std = _std(votes, mean_p)
    dissent = minority_dissent(votes, mean_p, std)
    return ConsensusResult(
        team_a_goals=goals_a,
        team_b_goals=goals_b,
        probability=mean_p,
        ci_low=ci_low,
        ci_high=ci_high,
        minority_dissent=dissent,
        all_votes=votes,
    )


@weave.op()
async def run_delphi_round(
    specialists: list[SpecialistDefinition],
    round1_votes: list[AgentVote],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    group: str = "",
) -> list[AgentVote]:
    """Round 2: Delphi signal + LangGraph Swarm revision (fallback: parallel W&B)."""
    if settings.use_langgraph_delphi:
        return await run_delphi_langgraph(
            specialists,
            round1_votes,
            match_query,
            team_a,
            team_b,
            contexts,
            group,
        )
    mean_p, ci_low, ci_high = weighted_consensus(round1_votes)
    delphi_addendum = (
        f"\n\n[DELPHI SIGNAL] Anonymous panel aggregate after round 1 (no individual "
        f"agent reasoning shown): P({team_a} wins)={mean_p:.3f}, "
        f"80% CI [{ci_low:.3f}, {ci_high:.3f}]. "
        f"Revise if your data warrants it. Contrarian: you may disagree with this "
        f"aggregate but still have not seen other specialists' round-1 votes."
    )
    delphi_specialists = [
        SpecialistDefinition(
            role=s.role,
            system_prompt=s.system_prompt + delphi_addendum,
            data_slice_id=s.data_slice_id,
        )
        for s in specialists
    ]
    return await run_swarm(
        delphi_specialists,
        match_query,
        team_a,
        team_b,
        contexts,
        round=2,
        group=group,
        model=settings.wandb_delphi_model,
    )
