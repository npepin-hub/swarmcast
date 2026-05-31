"""Delphi aggregation + round 2 (LangGraph Swarm or parallel W&B)."""
from __future__ import annotations

import asyncio

import weave

from ..config import settings
from ..schemas import AgentVote, ConsensusResult, SpecialistDefinition
from .consensus import _std, minority_dissent, weighted_consensus, weighted_score_consensus
from .inference import inference_chat
from .specialists import run_swarm


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


async def synthesize_verdict(
    match_query: str,
    consensus: ConsensusResult,
    round2_votes: list[AgentVote],
    team_a: str,
    team_b: str,
) -> str:
    """Write a 3-sentence narrative verdict from the round-2 votes."""
    vote_lines = "\n".join(
        f"- {v.role} (conf {v.confidence:.2f}): {v.probability:.0%} for {team_a} — {v.key_signal}"
        for v in round2_votes
    )
    dissent_lines = (
        "\n".join(f"- {v.role}: {v.reasoning[:120]}…" for v in consensus.minority_dissent)
        if consensus.minority_dissent else "None"
    )
    prompt = (
        f"Match: {match_query}\n"
        f"Swarm consensus: {consensus.probability:.1%} for {team_a} "
        f"(80% CI {consensus.ci_low:.1%}–{consensus.ci_high:.1%})\n\n"
        f"Round-2 specialist votes:\n{vote_lines}\n\n"
        f"Minority dissent:\n{dissent_lines}\n\n"
        "Write a 3-sentence verdict for a forecasting dashboard. "
        "Sentence 1: state the prediction and confidence level plainly. "
        "Sentence 2: name the 2-3 dominant signals that drove the consensus. "
        "Sentence 3: note the key uncertainty or dissenting view. "
        "Be direct. No hedging phrases like 'it appears' or 'it seems'. No markdown."
    )
    return await asyncio.to_thread(
        inference_chat,
        "You are a concise sports forecasting analyst.",
        prompt,
        settings.wandb_critic_model,
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
        from .swarm_langgraph import run_delphi_langgraph
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
        f"\n\n[DELPHI SIGNAL] Panel aggregate after round 1: "
        f"P({team_a} wins)={mean_p:.3f}, 80% CI [{ci_low:.3f}, {ci_high:.3f}]. "
        f"Revise if your data warrants it. Do not anchor without justification."
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
