"""Delphi aggregation + revision rounds 2..N (parallel W&B / optional LangGraph)."""
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
    final_votes: list[AgentVote],
    team_a: str,
    team_b: str,
    *,
    final_round: int = 2,
) -> str:
    """Write a 3-sentence narrative verdict from the final-round votes."""
    vote_lines = "\n".join(
        f"- {v.role} (conf {v.confidence:.2f}): {v.probability:.0%} for {team_a} — {v.key_signal}"
        for v in final_votes
    )
    dissent_lines = (
        "\n".join(f"- {v.role}: {v.reasoning[:120]}…" for v in consensus.minority_dissent)
        if consensus.minority_dissent
        else "None"
    )
    prompt = (
        f"Match: {match_query}\n"
        f"Swarm consensus: {consensus.probability:.1%} for {team_a} "
        f"(80% CI {consensus.ci_low:.1%}–{consensus.ci_high:.1%})\n\n"
        f"Round-{final_round} specialist votes:\n{vote_lines}\n\n"
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


def _delphi_addendum(
    round_num: int,
    prior_round: int,
    prior_votes: list[AgentVote],
    team_a: str,
) -> str:
    mean_p, ci_low, ci_high = weighted_consensus(prior_votes)
    return (
        f"\n\n[DELPHI ROUND {round_num}] Panel aggregate after round {prior_round}: "
        f"P({team_a} wins)={mean_p:.3f}, 80% CI [{ci_low:.3f}, {ci_high:.3f}]. "
        f"Revise if your data warrants it. Do not anchor without justification. "
        f"You MUST call submit_vote with your final forecast."
    )


@weave.op()
async def run_revision_round(
    specialists: list[SpecialistDefinition],
    prior_votes: list[AgentVote],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    round_num: int,
    group: str = "",
) -> list[AgentVote]:
    """Revision vote for round_num (2..deliberation_rounds), informed by prior round only."""
    if settings.use_langgraph_delphi:
        from .swarm_langgraph import run_delphi_langgraph

        return await run_delphi_langgraph(
            specialists,
            prior_votes,
            match_query,
            team_a,
            team_b,
            contexts,
            group,
            round_num=round_num,
        )

    prior_round = round_num - 1
    addendum = _delphi_addendum(round_num, prior_round, prior_votes, team_a)
    revised_specialists = [
        SpecialistDefinition(
            role=s.role,
            focus=s.focus,
            system_prompt=s.system_prompt + addendum,
            data_slice_id=s.data_slice_id,
        )
        for s in specialists
    ]
    return await run_swarm(
        revised_specialists,
        match_query,
        team_a,
        team_b,
        contexts,
        round=round_num,
        group=group,
        model=settings.wandb_delphi_model,
    )


# Back-compat alias
async def run_delphi_round(
    specialists: list[SpecialistDefinition],
    round1_votes: list[AgentVote],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    group: str = "",
) -> list[AgentVote]:
    return await run_revision_round(
        specialists,
        round1_votes,
        match_query,
        team_a,
        team_b,
        contexts,
        round_num=2,
        group=group,
    )
