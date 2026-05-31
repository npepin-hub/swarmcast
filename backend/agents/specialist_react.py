"""Specialist ReAct agent with MCP tools (W&B Inference + LangGraph)."""
from __future__ import annotations

import asyncio

import weave
from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON
from .mcp_tools import build_mcp_tools
from .vote_parse import parse_vote


def _chat_model(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.wandb_api_key,
        base_url=settings.wandb_inference_base_url,
        default_headers={"X-Wandb-Project": settings.weave_project_path},
    )


def _specialist_prompt(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    round: int,
    context: str,
) -> str:
    ctx_block = context.strip() or "(none — use MCP tools to fetch data)"
    return f"""You are {specialist.role}.
{specialist.system_prompt}

Match: {match_query}
Team A = {team_a}, Team B = {team_b}
Your data slice: {specialist.data_slice_id}
Round {round}.

You have MCP tools for WC2026 live data and historical World Cup records.
- Call tools as needed; betting/odds tools are not available.
- Team A and Team B are fixed for this fixture.

Pre-loaded context (may be partial):
{ctx_block}

When finished, respond with ONLY the vote JSON (no markdown):
{VOTE_JSON}
"""


def _last_ai_content(messages: list) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return str(msg.content)
    return ""


@weave.op()
def run_specialist_with_mcp(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int = 1,
    group: str = "",
    model: str | None = None,
) -> AgentVote:
    model = model or settings.wandb_specialist_model
    tools = build_mcp_tools(specialist.data_slice_id, team_a, team_b, group)
    prompt = _specialist_prompt(
        specialist, match_query, team_a, team_b, round, context
    )
    agent = create_react_agent(
        _chat_model(model),
        tools=tools,
        prompt=prompt,
    )
    result = agent.invoke(
        {"messages": [HumanMessage(content="Research this match and submit your vote.")]},
        {"recursion_limit": settings.specialist_mcp_recursion_limit},
    )
    raw = _last_ai_content(result.get("messages", []))
    return parse_vote(raw, specialist.role, round)


@weave.op()
async def run_specialist_with_mcp_async(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    context: str,
    round: int = 1,
    group: str = "",
    model: str | None = None,
) -> AgentVote:
    return await asyncio.to_thread(
        run_specialist_with_mcp,
        specialist,
        match_query,
        team_a,
        team_b,
        context,
        round,
        group,
        model,
    )
