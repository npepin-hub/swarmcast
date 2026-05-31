"""Specialist ReAct agent with MCP tools (W&B Inference + LangGraph)."""
from __future__ import annotations

import asyncio
import json
from typing import Annotated

import weave
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent
from openai import NotFoundError

from ..config import settings
from ..schemas import AgentVote, SpecialistDefinition
from .inference import VOTE_JSON
from .mcp_tools import build_mcp_tools
from .vote_parse import (
    ROUND1_ISOLATION,
    parse_vote,
    vote_from_payload,
    vote_text_from_messages,
)


def _chat_model(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        api_key=settings.wandb_api_key,
        base_url=settings.wandb_inference_base_url,
        default_headers={"X-Wandb-Project": settings.weave_project_path},
    )


def _contrarian_hint(round: int, isolated: bool) -> str:
    if round == 1 or isolated:
        return (
            "\nYou are the contrarian: challenge the favourite / mainstream narrative "
            "using only your data and MCP tools — not other specialists' views.\n"
        )
    return (
        "\nYou are the contrarian: you may disagree with the Delphi panel aggregate, "
        "but you still have NOT seen individual agents' round-1 reasoning.\n"
    )


def _build_submit_vote_tool(capture: dict) -> object:
    @tool
    def submit_vote(
        team_a_goals: Annotated[int, "Predicted goals for Team A (>= 0)"],
        team_b_goals: Annotated[int, "Predicted goals for Team B (>= 0)"],
        probability: Annotated[float, "P(Team A wins), 0.0 to 1.0"],
        confidence: Annotated[float, "Confidence in your estimate, 0.0 to 1.0"],
        key_signal: Annotated[str, "One-line key signal"],
        reasoning: Annotated[str, "Brief reasoning (<= 200 words)"],
        uncertainty_flag: Annotated[bool, "True if low data confidence"] = False,
    ) -> str:
        """Submit your final match forecast. You must call this once before finishing."""
        capture.clear()
        capture.update(
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
        return "Vote recorded."

    return submit_vote


def _specialist_prompt(
    specialist: SpecialistDefinition,
    match_query: str,
    team_a: str,
    team_b: str,
    round: int,
    context: str,
    *,
    isolated: bool = False,
) -> str:
    ctx_block = context.strip() or "(none — use MCP tools to fetch data)"
    if isolated or round == 1:
        isolation = ROUND1_ISOLATION
    else:
        isolation = (
            "\nROUND 2+: You may use the Delphi aggregate below. "
            "You have NOT seen other agents' individual round-1 votes or reasoning.\n"
        )
    contrarian = ""
    if specialist.role == "contrarian":
        contrarian = _contrarian_hint(round, isolated)
        contrarian += (
            "\nContrarian mandate: argue for the underdog. If Team A is the favourite, "
            "P(Team A wins) should usually be below 0.5 unless data strongly says otherwise.\n"
        )
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
- When finished researching, call submit_vote exactly once with your final forecast.
- Do not end without calling submit_vote.

Pre-loaded context (may be partial):
{ctx_block}

If submit_vote fails, you may instead respond with ONLY this JSON (no markdown):
{VOTE_JSON}
"""


def _recursion_limit(specialist: SpecialistDefinition) -> int:
    base = settings.specialist_mcp_recursion_limit
    if specialist.role == "contrarian":
        return base + settings.specialist_contrarian_extra_steps
    return base


def _vote_from_messages(messages: list, role: str, round: int) -> AgentVote | None:
    for msg in reversed(messages):
        if isinstance(msg, ToolMessage) and msg.name == "submit_vote":
            try:
                payload = json.loads(msg.content) if isinstance(msg.content, str) else {}
            except json.JSONDecodeError:
                payload = {}
            if not payload and hasattr(msg, "artifact"):
                payload = msg.artifact or {}
            if payload:
                return vote_from_payload(payload, role, round)
    return None


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
    *,
    isolated: bool = False,
) -> AgentVote:
    if model is None and specialist.role == "contrarian":
        model = settings.wandb_contrarian_model
    model = model or settings.wandb_specialist_model
    capture: dict = {}
    tools = build_mcp_tools(specialist.data_slice_id, team_a, team_b, group)
    tools.append(_build_submit_vote_tool(capture))
    prompt = _specialist_prompt(
        specialist, match_query, team_a, team_b, round, context, isolated=isolated
    )
    fallback = settings.wandb_specialist_model
    models_to_try = [model] if model == fallback else [model, fallback]
    result = None
    for attempt_model in models_to_try:
        agent = create_react_agent(
            _chat_model(attempt_model),
            tools=tools,
            prompt=prompt,
        )
        try:
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
            break
        except NotFoundError:
            if attempt_model == fallback:
                raise
            print(
                f"[{specialist.role}] model {attempt_model} not found on W&B Inference, "
                f"falling back to {fallback}"
            )
    messages = (result or {}).get("messages", [])
    if capture:
        return vote_from_payload(capture, specialist.role, round)
    tool_vote = _vote_from_messages(messages, specialist.role, round)
    if tool_vote:
        return tool_vote
    raw = vote_text_from_messages(messages) or _last_ai_content(messages)
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
    *,
    isolated: bool = False,
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
        isolated=isolated,
    )
