"""MCP tool registry — wc26-mcp and @zafronix/wc-mcp (no betting odds)."""
from __future__ import annotations

from dataclasses import dataclass

from .wc26 import call_wc26, call_wc_history

# Tools allowed per specialist data_slice_id (see requirements/data_and_prompts.md)
SLICE_TOOL_NAMES: dict[str, list[str]] = {
    "statsbomb": [
        "wc26_get_team_profile",
        "wc26_compare_teams",
        "wc26_get_historical_matchups",
        "history_get_team",
    ],
    "kaggle_history": [
        "wc26_get_historical_matchups",
        "history_get_team",
        "history_get_team_roster",
        "history_list_matches",
    ],
    "live_form": [
        "wc26_get_matches",
        "wc26_get_news",
        "wc26_what_to_know_now",
    ],
    "live_injuries": [
        "wc26_get_injuries",
        "wc26_get_news",
    ],
    "live_standings": [
        "wc26_get_standings",
        "wc26_get_groups",
        "wc26_get_bracket",
    ],
    "contrarian": [
        "wc26_compare_teams",
        "wc26_get_team_profile",
        "wc26_get_historical_matchups",
        "wc26_what_to_know_now",
        "history_get_team",
    ],
}

# Default when orchestrator assigns another slice id (e.g. wc26, tactical_analyst)
DEFAULT_TOOL_NAMES: list[str] = [
    "wc26_get_team_profile",
    "wc26_compare_teams",
    "wc26_get_historical_matchups",
    "wc26_get_matches",
    "wc26_get_injuries",
    "wc26_get_news",
    "wc26_get_standings",
    "wc26_what_to_know_now",
    "history_get_team",
    "history_get_historical_matchups",
]


@dataclass(frozen=True)
class McpToolSpec:
    name: str
    description: str


TOOL_SPECS: dict[str, McpToolSpec] = {
    "wc26_get_team_profile": McpToolSpec(
        "wc26_get_team_profile",
        "WC2026 team profile: coach, style, key players, rankings (not betting odds).",
    ),
    "wc26_compare_teams": McpToolSpec(
        "wc26_compare_teams",
        "Side-by-side WC2026 comparison of Team A vs Team B for this fixture.",
    ),
    "wc26_get_historical_matchups": McpToolSpec(
        "wc26_get_historical_matchups",
        "All WC2026-era meetings between Team A and Team B.",
    ),
    "wc26_get_matches": McpToolSpec(
        "wc26_get_matches",
        "Recent/upcoming WC2026 fixtures for a team. Pass team name or FIFA code.",
    ),
    "wc26_get_injuries": McpToolSpec(
        "wc26_get_injuries",
        "Injury and availability report for a team.",
    ),
    "wc26_get_news": McpToolSpec(
        "wc26_get_news",
        "Latest news for a team (limit default 5).",
    ),
    "wc26_get_standings": McpToolSpec(
        "wc26_get_standings",
        "WC2026 group standings (optional group letter).",
    ),
    "wc26_get_groups": McpToolSpec(
        "wc26_get_groups",
        "WC2026 group composition and schedule.",
    ),
    "wc26_get_bracket": McpToolSpec(
        "wc26_get_bracket",
        "WC2026 knockout bracket.",
    ),
    "wc26_what_to_know_now": McpToolSpec(
        "wc26_what_to_know_now",
        "Temporal briefing: what matters in the tournament right now.",
    ),
    "history_get_team": McpToolSpec(
        "history_get_team",
        "Historical World Cup record for a nation (1930–2026).",
    ),
    "history_get_team_roster": McpToolSpec(
        "history_get_team_roster",
        "Full World Cup squad for a team in a given year.",
    ),
    "history_list_matches": McpToolSpec(
        "history_list_matches",
        "List historical WC matches (filter by year, stage, or date).",
    ),
    "history_get_historical_matchups": McpToolSpec(
        "history_get_historical_matchups",
        "Alias: use wc26_get_historical_matchups for this fixture's teams.",
    ),
}


def tool_names_for_slice(data_slice_id: str) -> list[str]:
    return SLICE_TOOL_NAMES.get(data_slice_id, DEFAULT_TOOL_NAMES)


def invoke_tool(name: str, arguments: dict) -> str:
    """Run one MCP tool synchronously (cached in wc26.py)."""
    if name == "wc26_get_team_profile":
        return call_wc26("get_team_profile", {"team": arguments["team"]})
    if name == "wc26_compare_teams":
        return call_wc26(
            "compare_teams",
            {"team_a": arguments["team_a"], "team_b": arguments["team_b"]},
        )
    if name == "wc26_get_historical_matchups":
        return call_wc26(
            "get_historical_matchups",
            {"team_a": arguments["team_a"], "team_b": arguments["team_b"]},
        )
    if name == "wc26_get_matches":
        params: dict = {"team": arguments["team"]}
        for key in ("date", "group", "round", "status"):
            if arguments.get(key):
                params[key] = arguments[key]
        return call_wc26("get_matches", params)
    if name == "wc26_get_injuries":
        params = {"team": arguments["team"]}
        if arguments.get("status"):
            params["status"] = arguments["status"]
        return call_wc26("get_injuries", params)
    if name == "wc26_get_news":
        params = {"team": arguments["team"], "limit": int(arguments.get("limit", 5))}
        if arguments.get("category"):
            params["category"] = arguments["category"]
        return call_wc26("get_news", params)
    if name == "wc26_get_standings":
        params = {}
        if arguments.get("group"):
            params["group"] = arguments["group"]
        return call_wc26("get_standings", params)
    if name == "wc26_get_groups":
        params = {}
        if arguments.get("group"):
            params["group"] = arguments["group"]
        return call_wc26("get_groups", params)
    if name == "wc26_get_bracket":
        params = {}
        if arguments.get("round"):
            params["round"] = arguments["round"]
        return call_wc26("get_bracket", params)
    if name == "wc26_what_to_know_now":
        return call_wc26("what_to_know_now", {})
    if name == "history_get_team":
        return call_wc_history("get_team", {"name": arguments["name"]})
    if name == "history_get_team_roster":
        return call_wc_history(
            "get_team_roster",
            {"name": arguments["name"], "year": int(arguments["year"])},
        )
    if name == "history_list_matches":
        params = {}
        for key in ("year", "stage", "date"):
            if arguments.get(key):
                params[key] = arguments[key]
        return call_wc_history("list_matches", params)
    if name == "history_get_historical_matchups":
        return call_wc26(
            "get_historical_matchups",
            {"team_a": arguments["team_a"], "team_b": arguments["team_b"]},
        )
    return f"Unknown tool: {name}"
