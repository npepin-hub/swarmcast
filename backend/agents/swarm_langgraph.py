"""LangGraph Swarm — Delphi round 2 with per-agent threads (avoids context blow-up)."""
from __future__ import annotations

import asyncio
import uuid

import weave
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .consensus import weighted_consensus
from .inference import VOTE_JSON, extract_json_object
from .specialist_react import run_specialist_with_mcp_async
from .vote_parse import parse_vote

ORCHESTRATOR_NAME = "orchestrator"
ORCHESTRATOR_PROMPT = """You coordinate the Delphi revision round.
Hand off to each specialist so they can submit a revised probability vote, then summarize.
"""

_swarm_cache: dict[frozenset[str], object] = {}


def _chat_model(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.wandb_api_key,
        base_url=settings.wandb_inference_base_url,
        default_headers={"X-Wandb-Project": settings.weave_project_path},
    )


def _build_swarm(roles: list[str]) -> object:
    key = frozenset(roles)
    if key in _swarm_cache:
        return _swarm_cache[key]
    model = _chat_model(settings.wandb_delphi_model)
    handoffs = [
        create_handoff_tool(agent_name=r, description=f"Hand off to {r} for revised vote")
        for r in roles
    ]
    orchestrator = create_react_agent(
        model,
        tools=handoffs,
        prompt=ORCHESTRATOR_PROMPT,
        name=ORCHESTRATOR_NAME,
    )
    agents = [orchestrator]
    for role in roles:
        agents.append(
            create_react_agent(
                model,
                tools=[
                    create_handoff_tool(
                        agent_name=ORCHESTRATOR_NAME,
                        description="Return to orchestrator after revised vote",
                    )
                ],
                prompt=f"You are {role}. Revise your vote when asked. {VOTE_JSON}",
                name=role,
            )
        )
    from langgraph_swarm import SwarmState

    class State(SwarmState):
        pass

    workflow = create_swarm(agents, default_active_agent=ORCHESTRATOR_NAME, state_schema=State)
    app = workflow.compile(checkpointer=InMemorySaver())
    _swarm_cache[key] = app
    return app


def _extract_vote(messages: list, role: str) -> AgentVote | None:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and getattr(msg, "name", None) == role:
            vote = parse_vote(str(msg.content), role, 2)
            if vote.uncertainty_flag and vote.key_signal == "parse_error":
                continue
            return vote
    return None


@weave.op()
async def run_delphi_langgraph(
    specialists: list[SpecialistDefinition],
    round1_votes: list[AgentVote],
    match_query: str,
    team_a: str,
    team_b: str,
    contexts: dict[str, str],
    group: str = "",
) -> list[AgentVote]:
    """Delphi round 2: sparse signal + LangGraph Swarm revision per specialist."""
    mean_p, ci_low, ci_high = weighted_consensus(round1_votes)
    delphi_signal = (
        f"[DELPHI SIGNAL] After round 1: P({team_a} wins)={mean_p:.3f}, "
        f"80% CI [{ci_low:.3f}, {ci_high:.3f}]. "
        "Revise only if your data warrants it."
    )
    roles = [s.role for s in specialists]
    app = _build_swarm(roles)
    default_ctx = "\n\n".join(contexts.values()) if contexts else ""
    revised: list[AgentVote] = []

    for spec in specialists:
        ctx = contexts.get(spec.data_slice_id, default_ctx)
        prompt = (
            f"{spec.system_prompt}\n\n{delphi_signal}\n\n"
            f"Match: {match_query}\nTeam A={team_a}, Team B={team_b}\n"
            f"Context:\n{ctx}\n\nSubmit revised score and win probability. {VOTE_JSON}"
        )
        seed = HumanMessage(content=prompt)
        config = {
            "configurable": {"thread_id": str(uuid.uuid4())},
            "recursion_limit": 25,
        }
        result = await asyncio.to_thread(
            app.invoke,
            {"messages": [seed], "active_agent": spec.role},
            config,
        )
        vote = _extract_vote(result.get("messages", []), spec.role)
        if vote:
            revised.append(vote)
        else:
            vote = await run_specialist_with_mcp_async(
                spec,
                match_query,
                team_a,
                team_b,
                f"{delphi_signal}\n\n{ctx}",
                round=2,
                group=group,
                model=settings.wandb_delphi_model,
            )
            revised.append(vote)

    return revised
