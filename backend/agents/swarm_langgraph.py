"""LangGraph Swarm — Delphi revision rounds (parallel MCP specialists)."""
from __future__ import annotations

import weave

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .consensus import weighted_consensus
from .specialists import run_swarm


def _delphi_addendum(round_num: int, prior_round: int, prior_votes, team_a: str) -> str:
    mean_p, ci_low, ci_high = weighted_consensus(prior_votes)
    return (
        f"\n\n[DELPHI ROUND {round_num}] Panel aggregate after round {prior_round}: "
        f"P({team_a} wins)={mean_p:.3f}, 80% CI [{ci_low:.3f}, {ci_high:.3f}]. "
        f"Revise if your data warrants it. Do not anchor without justification. "
        f"You MUST call submit_vote with your final forecast."
    )


@weave.op()
async def run_delphi_langgraph(
    specialists: list[SpecialistDefinition],
    prior_votes: list[AgentVote],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    group: str = "",
    round_num: int = 2,
) -> list[AgentVote]:
    """Revision round via parallel MCP specialists (reliable votes including contrarian)."""
    prior_round = round_num - 1
    addendum = _delphi_addendum(round_num, prior_round, prior_votes, team_a)
    revised = [
        SpecialistDefinition(
            role=s.role,
            focus=s.focus,
            system_prompt=s.system_prompt + addendum,
            data_slice_id=s.data_slice_id,
        )
        for s in specialists
    ]
    return await run_swarm(
        revised,
        match_query,
        team_a,
        team_b,
        contexts,
        round=round_num,
        group=group,
        model=settings.wandb_delphi_model,
    )
