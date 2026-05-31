"""LangChain tools wrapping wc26 / history MCP for specialist ReAct agents."""
from __future__ import annotations

from typing import Annotated

from langchain_core.tools import BaseTool, tool

from ..data.mcp_registry import invoke_tool, tool_names_for_slice


def build_mcp_tools(
    data_slice_id: str,
    team_a: str,
    team_b: str,
    group: str = "",
) -> list[BaseTool]:
    """Build MCP tools for a specialist's data slice (fixture teams bound where needed)."""
    names = tool_names_for_slice(data_slice_id)
    tools: list[BaseTool] = []
    fixture_group = group

    if "wc26_get_team_profile" in names:

        @tool
        def wc26_get_team_profile(
            team: Annotated[str, "Team name or FIFA code (e.g. MEX, Mexico)"],
        ) -> str:
            """WC2026 team profile: coach, style, key players, rankings."""
            return invoke_tool("wc26_get_team_profile", {"team": team})

        tools.append(wc26_get_team_profile)

    if "wc26_compare_teams" in names:

        @tool
        def wc26_compare_teams() -> str:
            """Side-by-side WC2026 comparison of Team A vs Team B for this fixture."""
            return invoke_tool(
                "wc26_compare_teams", {"team_a": team_a, "team_b": team_b}
            )

        tools.append(wc26_compare_teams)

    if "wc26_get_historical_matchups" in names:

        @tool
        def wc26_get_historical_matchups() -> str:
            """WC meetings between Team A and Team B for this fixture."""
            return invoke_tool(
                "wc26_get_historical_matchups", {"team_a": team_a, "team_b": team_b}
            )

        tools.append(wc26_get_historical_matchups)

    if "wc26_get_matches" in names:

        @tool
        def wc26_get_matches(
            team: Annotated[str, "Team name or FIFA code"],
            date: Annotated[str, "Optional date filter"] = "",
            status: Annotated[str, "Optional status filter"] = "",
        ) -> str:
            """WC2026 fixtures for a team."""
            return invoke_tool(
                "wc26_get_matches",
                {"team": team, "date": date, "status": status},
            )

        tools.append(wc26_get_matches)

    if "wc26_get_injuries" in names:

        @tool
        def wc26_get_injuries(
            team: Annotated[str, "Team name or FIFA code"],
            status: Annotated[str, "Optional injury status filter"] = "",
        ) -> str:
            """Injury and availability for a team."""
            return invoke_tool("wc26_get_injuries", {"team": team, "status": status})

        tools.append(wc26_get_injuries)

    if "wc26_get_news" in names:

        @tool
        def wc26_get_news(
            team: Annotated[str, "Team name or FIFA code"],
            limit: Annotated[int, "Max articles"] = 5,
        ) -> str:
            """Latest WC2026 news for a team."""
            return invoke_tool("wc26_get_news", {"team": team, "limit": limit})

        tools.append(wc26_get_news)

    if "wc26_get_standings" in names:

        @tool
        def wc26_get_standings(
            group_letter: Annotated[str, "Group letter; empty uses match group"] = "",
        ) -> str:
            """WC2026 group standings."""
            g = group_letter or fixture_group
            return invoke_tool("wc26_get_standings", {"group": g})

        tools.append(wc26_get_standings)

    if "wc26_get_groups" in names:

        @tool
        def wc26_get_groups(
            group_letter: Annotated[str, "Group letter filter"] = "",
        ) -> str:
            """WC2026 group composition and schedule."""
            return invoke_tool("wc26_get_groups", {"group": group_letter or fixture_group})

        tools.append(wc26_get_groups)

    if "wc26_get_bracket" in names:

        @tool
        def wc26_get_bracket(
            round: Annotated[str, "Knockout round name"] = "",
        ) -> str:
            """WC2026 knockout bracket."""
            return invoke_tool("wc26_get_bracket", {"round": round})

        tools.append(wc26_get_bracket)

    if "wc26_what_to_know_now" in names:

        @tool
        def wc26_what_to_know_now() -> str:
            """What matters in the WC2026 tournament right now."""
            return invoke_tool("wc26_what_to_know_now", {})

        tools.append(wc26_what_to_know_now)

    if "history_get_team" in names:

        @tool
        def history_get_team(
            name: Annotated[str, "Nation name or common name"],
        ) -> str:
            """Historical World Cup record (1930–2026) for a nation."""
            return invoke_tool("history_get_team", {"name": name})

        tools.append(history_get_team)

    if "history_get_team_roster" in names:

        @tool
        def history_get_team_roster(
            name: Annotated[str, "Nation name"],
            year: Annotated[int, "World Cup year"],
        ) -> str:
            """World Cup squad for a team in a given year."""
            return invoke_tool("history_get_team_roster", {"name": name, "year": year})

        tools.append(history_get_team_roster)

    if "history_list_matches" in names:

        @tool
        def history_list_matches(
            year: Annotated[int, "World Cup year; 0 for no filter"] = 0,
            stage: Annotated[str, "Stage filter"] = "",
        ) -> str:
            """List historical World Cup matches."""
            args: dict = {}
            if year:
                args["year"] = year
            if stage:
                args["stage"] = stage
            return invoke_tool("history_list_matches", args)

        tools.append(history_list_matches)

    if "history_get_historical_matchups" in names:

        @tool
        def history_get_historical_matchups() -> str:
            """Historical WC meetings between Team A and Team B."""
            return invoke_tool(
                "history_get_historical_matchups",
                {"team_a": team_a, "team_b": team_b},
            )

        tools.append(history_get_historical_matchups)

    return tools
