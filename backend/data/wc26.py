"""WC26 MCP client — replaces static RAG + live API data with wc26-mcp tools.

Each _call() spins up `npx -y wc26-mcp`, sends an initialize + tools/call over
stdin, and returns the text content.  Results are cached for the session (TTL 1h).
"""
from __future__ import annotations
import json
import subprocess
import time

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


def build_context_bundle(
    team_a: str,
    team_b: str,
    group: str = "",
) -> dict[str, str]:
    """Return context slices keyed by data_slice_id, sourced live from wc26-mcp."""
    profile_a  = _call("get_team_profile",       {"team": team_a})
    profile_b  = _call("get_team_profile",       {"team": team_b})
    compare    = _call("compare_teams",           {"team_a": team_a, "team_b": team_b})
    h2h        = _call("get_historical_matchups", {"team_a": team_a, "team_b": team_b})
    matches_a  = _call("get_matches",             {"team": team_a})
    matches_b  = _call("get_matches",             {"team": team_b})
    news_a     = _call("get_news",                {"team": team_a, "limit": 5})
    news_b     = _call("get_news",                {"team": team_b, "limit": 5})
    injuries_a = _call("get_injuries",            {"team": team_a})
    injuries_b = _call("get_injuries",            {"team": team_b})
    standings  = _call("get_standings",           {"group": group} if group else {})

    return {
        "statsbomb": (
            f"## Team Profiles\n\n### {team_a}\n{profile_a}"
            f"\n\n### {team_b}\n{profile_b}"
            f"\n\n## Head-to-Head Comparison\n{compare}"
        ),
        "kaggle_history": h2h,
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
