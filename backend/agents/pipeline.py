"""Single SwarmCast deliberation pipeline — original agents + W&B + Delphi rounds."""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import weave

from ..config import settings
from ..schemas import AgentVote, ConsensusResult, CritiqueOutput, SpecialistDefinition, WSEventType
from .critic import run_critic
from .delphi import aggregate, run_revision_round
from .orchestrator import act_on_critique, ensure_contrarian, spawn_specialists
from .specialists import run_swarm

EmitFn = Callable[[WSEventType, Any], Awaitable[None]] | None


@dataclass
class DeliberationResult:
    swarm_run_id: str
    specialists: list[SpecialistDefinition]
    round_votes: list[list[AgentVote]] = field(default_factory=list)
    critique: CritiqueOutput | None = None
    consensus: ConsensusResult | None = None

    @property
    def round1_votes(self) -> list[AgentVote]:
        return self.round_votes[0] if self.round_votes else []

    @property
    def round2_votes(self) -> list[AgentVote]:
        return self.round_votes[-1] if self.round_votes else []


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
    n_rounds = settings.deliberation_rounds
    with weave.attributes(
        {
            "swarm_run_id": swarm_run_id,
            "team_a": team_a,
            "team_b": team_b,
            "match_date": match_date,
            "competition": competition,
            "competition_id": group,
            "deliberation_rounds": n_rounds,
        }
    ):
        specialists = ensure_contrarian(spawn_specialists(match_query, team_a, team_b))
        if emit:
            await emit(WSEventType.spawning, [s.model_dump() for s in specialists])

        round_votes: list[list[AgentVote]] = []
        r1 = await run_swarm(
            specialists,
            match_query,
            team_a,
            team_b,
            contexts,
            round=1,
            group=group,
            isolated=True,
        )
        round_votes.append(r1)
        if emit:
            for v in r1:
                await emit(WSEventType.agent_vote, v.model_dump())

        critique = run_critic(r1, match_query)
        if emit:
            await emit(WSEventType.critic_fired, critique.model_dump())

        specialists = act_on_critique(critique, specialists, match_query)
        specialists = ensure_contrarian(specialists)

        prior = r1
        for round_num in range(2, n_rounds + 1):
            prior = await run_revision_round(
                specialists,
                prior,
                match_query,
                team_a,
                team_b,
                contexts,
                round_num,
                group,
            )
            round_votes.append(prior)
            if emit:
                for v in prior:
                    await emit(WSEventType.delphi_round, v.model_dump())

        consensus = aggregate(round_votes[-1])
        if emit:
            await emit(
                WSEventType.consensus,
                {
                    **consensus.model_dump(),
                    "swarm_run_id": swarm_run_id,
                    "deliberation_rounds": n_rounds,
                    "round_votes": [
                        [v.model_dump() for v in round] for round in round_votes
                    ],
                },
            )

    return DeliberationResult(
        swarm_run_id=swarm_run_id,
        specialists=specialists,
        round_votes=round_votes,
        critique=critique,
        consensus=consensus,
    )
