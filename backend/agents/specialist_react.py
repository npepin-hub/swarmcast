"""Specialist ReAct agent with MCP tools (W&B Inference + LangGraph)."""
from __future__ import annotations

import asyncio
import json

import weave
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON
from .mcp_tools import build_mcp_tools
from .vote_parse import ROUND1_ISOLATION, parse_vote, vote_text_from_messages


def _chat_model(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.wandb_api_key,
        base_url=settings.wandb_inference_base_url,
        default_headers={"X-Wandb-Project": settings.weave_project_path},
    )


def _contrarian_hint(round: int) -> str:
    if round != 1:
        return (
            "\nYou are the contrarian: you may disagree with the Delphi panel aggregate, "
            "but you still have NOT seen individual agents' round-1 reasoning.\n"
        )
    return (
        "\nYou are the contrarian: challenge the favourite / mainstream narrative "
        "using only your data and MCP tools — not other specialists' views "
        "(which you cannot see in round 1).\n"
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
    isolation = ROUND1_ISOLATION if round == 1 else (
        "\nROUND 2: You may use the Delphi aggregate below. "
        "You have NOT seen other agents' individual round-1 votes or reasoning.\n"
    )
    contrarian = _contrarian_hint(round) if specialist.role == "contrarian" else ""
    return f"""You are {specialist.role}.
{specialist.system_prompt}
{contrarian}
{isolation}

Match: {match_query}
Team A = {team_a}, Team B = {team_b}
Your data slice: {specialist.data_slice_id}
Round {round}.

You have MCP tools for WC2026 live data and historical World Cup records.
- Call tools as needed; betting/odds tools are not available.
- Team A and Team B are fixed for this fixture.
- You MUST call submit_vote (preferred) or end with ONLY the vote JSON.

Pre-loaded context (may be partial):
{ctx_block}

Vote schema:
{VOTE_JSON}
"""


def _make_submit_vote_tool() -> object:
    @tool
    def submit_vote(
        team_a_goals: int,
        team_b_goals: int,
        probability: float,
        confidence: float,
        key_signal: str,
        reasoning: str,
        uncertainty_flag: bool = False,
    ) -> str:
        """Submit your final independent forecast vote. Call once when done researching."""
        return json.dumps(
            {
                "team_a_goals": team_a_goals,
                "team_b_goals": team_b_goals,
                "probability": probability,
                "confidence": confidence,
                "key_signal": key_signal,
                "reasoning": reasoning,
                "uncertainty_flag": uncertainty_flag,
            }
        )

    return submit_vote


def _recursion_limit(specialist: SpecialistDefinition) -> int:
    base = settings.specialist_mcp_recursion_limit
    if specialist.role == "contrarian":
        return base + settings.specialist_contrarian_extra_steps
    return base


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
    tools.append(_make_submit_vote_tool())
    prompt = _specialist_prompt(
        specialist, match_query, team_a, team_b, round, context
    )
    agent = create_react_agent(
        _chat_model(model),
        tools=tools,
        prompt=prompt,
    )
    result = agent.invoke(
        {
            "messages": [
                HumanMessage(
                    content=(
                        "Research this match using MCP tools, then call submit_vote "
                        "with your independent forecast."
                    )
                )
            ]
        },
        {"recursion_limit": _recursion_limit(specialist)},
    )
    messages = result.get("messages", [])
    raw = vote_text_from_messages(messages)
    if not raw:
        raw = ""
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                raw = str(msg.content)
                break
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
