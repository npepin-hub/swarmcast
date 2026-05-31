"""WC26 + WC-history MCP clients — replaces static RAG + live API data.

Two MCP servers:
  wc26-mcp             — WC2026 fixtures, teams, news, injuries, odds
  @zafronix/wc-mcp    — Historical WC data 1930-2026 (matches, rosters, brackets)

Each _call*() spins up the relevant npx server, sends initialize + tools/call
over stdin, and returns the text content.  Results are cached 1h.
"""
from __future__ import annotations
import asyncio
import json
import os
import subprocess
import time
from ..config import settings

_TTL = 3600
_cache: dict[str, tuple[float, str]] = {}


def _call(tool: str, params: dict) -> str:
    key = f"{tool}:{json.dumps(params, sort_keys=True)}"
    now = time.time()
    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]

    stdin = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "swarmcast", "version": "1"}}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool, "arguments": params}}) + "\n"
    )
    proc = subprocess.run(
        ["npx", "-y", "wc26-mcp"],
        input=stdin, capture_output=True, text=True, timeout=30,
    )
    text = ""
    for line in proc.stdout.strip().splitlines():
        try:
            resp = json.loads(line)
            if resp.get("id") == 2:
                content = resp.get("result", {}).get("content", [])
                text = "\n".join(c["text"] for c in content if c.get("type") == "text")
                break
        except Exception:
            continue

    _cache[key] = (now, text)
    return text


def _call_history(tool: str, params: dict) -> str:
    """Call a @zafronix/wc-mcp tool (historical WC data 1930-2026)."""
    key = f"wc:{tool}:{json.dumps(params, sort_keys=True)}"
    now = time.time()
    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]

    stdin = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "swarmcast", "version": "1"}}}) + "\n" +
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                    "params": {"name": tool, "arguments": params}}) + "\n"
    )
    env = {**os.environ, "WC_API_KEY": settings.wc_api_key}
    proc = subprocess.run(
        ["npx", "-y", "@zafronix/wc-mcp"],
        input=stdin, capture_output=True, text=True, timeout=30, env=env,
    )
    text = ""
    for line in proc.stdout.strip().splitlines():
        try:
            resp = json.loads(line)
            if resp.get("id") == 2:
                content = resp.get("result", {}).get("content", [])
                text = "\n".join(c["text"] for c in content if c.get("type") == "text")
                break
        except Exception:
            continue

    _cache[key] = (now, text)
    return text


async def build_context_bundle(
    team_a: str,
    team_b: str,
    group: str = "",
) -> dict[str, str]:
    """Return context slices keyed by data_slice_id, sourced live from wc26-mcp.
    All 13 MCP subprocess calls run concurrently via asyncio.gather.
    """
    (
        profile_a, profile_b, compare, h2h,
        hist_team_a, hist_team_b,
        matches_a, matches_b,
        news_a, news_b,
        injuries_a, injuries_b,
        standings,
    ) = await asyncio.gather(
        asyncio.to_thread(_call, "get_team_profile",        {"team": team_a}),
        asyncio.to_thread(_call, "get_team_profile",        {"team": team_b}),
        asyncio.to_thread(_call, "compare_teams",           {"team_a": team_a, "team_b": team_b}),
        asyncio.to_thread(_call, "get_historical_matchups", {"team_a": team_a, "team_b": team_b}),
        asyncio.to_thread(_call_history, "get_team",        {"name": team_a}),
        asyncio.to_thread(_call_history, "get_team",        {"name": team_b}),
        asyncio.to_thread(_call, "get_matches",             {"team": team_a}),
        asyncio.to_thread(_call, "get_matches",             {"team": team_b}),
        asyncio.to_thread(_call, "get_news",                {"team": team_a, "limit": 5}),
        asyncio.to_thread(_call, "get_news",                {"team": team_b, "limit": 5}),
        asyncio.to_thread(_call, "get_injuries",            {"team": team_a}),
        asyncio.to_thread(_call, "get_injuries",            {"team": team_b}),
        asyncio.to_thread(_call, "get_standings",           {"group": group} if group else {}),
    )

    return {
        "statsbomb": (
            f"## Team Profiles\n\n### {team_a}\n{profile_a}"
            f"\n\n### {team_b}\n{profile_b}"
            f"\n\n## Head-to-Head Comparison\n{compare}"
        ),
        "kaggle_history": (
            f"## WC2026 Head-to-Head\n{h2h}"
            f"\n\n## Historical WC Record\n\n### {team_a}\n{hist_team_a}"
            f"\n\n### {team_b}\n{hist_team_b}"
        ),
        "live_form": (
            f"## Recent Matches\n\n### {team_a}\n{matches_a}"
            f"\n\n### {team_b}\n{matches_b}"
            f"\n\n## Latest News\n\n### {team_a}\n{news_a}"
            f"\n\n### {team_b}\n{news_b}"
        ),
        "live_injuries": (
            f"## Injury Reports\n\n### {team_a}\n{injuries_a}"
            f"\n\n### {team_b}\n{injuries_b}"
        ),
        "live_standings": standings,
    }
