"""Single SwarmCast deliberation pipeline — original agents + W&B + LangGraph Delphi."""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import weave

from ..schemas import AgentVote, ConsensusResult, CritiqueOutput, SpecialistDefinition, WSEventType
from .critic import run_critic
from .delphi import aggregate, run_delphi_round
from .orchestrator import act_on_critique, spawn_specialists
from .specialists import run_swarm

EmitFn = Callable[[WSEventType, Any], Awaitable[None]] | None


@dataclass
class DeliberationResult:
    swarm_run_id: str
    specialists: list[SpecialistDefinition]
    round1_votes: list[AgentVote]
    round2_votes: list[AgentVote]
    critique: CritiqueOutput
    consensus: ConsensusResult


@weave.op()
async def run_deliberation(
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    emit: EmitFn = None,
    group: str = "",
    match_date: str = "",
    competition: str = "",
) -> DeliberationResult:
    swarm_run_id = str(uuid.uuid4())
    with weave.attributes(
        {
            "swarm_run_id": swarm_run_id,
            "team_a": team_a,
            "team_b": team_b,
            "match_date": match_date,
            "competition": competition,
            "competition_id": group,
        }
    ):
        specialists = spawn_specialists(match_query, team_a, team_b)
        if emit:
            await emit(WSEventType.spawning, [s.model_dump() for s in specialists])

        round1_votes = await run_swarm(
            specialists, match_query, team_a, team_b, contexts, round=1, group=group
        )
        if emit:
            for v in round1_votes:
                await emit(WSEventType.agent_vote, v.model_dump())

        critique = run_critic(round1_votes, match_query)
        if emit:
            await emit(WSEventType.critic_fired, critique.model_dump())

        specialists = act_on_critique(critique, specialists, match_query)
        round2_votes = await run_delphi_round(
            specialists,
            round1_votes,
            match_query,
            team_a,
            team_b,
            contexts,
            group,
        )
        if emit:
            for v in round2_votes:
                await emit(WSEventType.delphi_round, v.model_dump())

        consensus = aggregate(round2_votes)
        if emit:
            await emit(
                WSEventType.consensus,
                {**consensus.model_dump(), "swarm_run_id": swarm_run_id},
            )

    return DeliberationResult(
        swarm_run_id=swarm_run_id,
        specialists=specialists,
        round1_votes=round1_votes,
        round2_votes=round2_votes,
        critique=critique,
        consensus=consensus,
    )
