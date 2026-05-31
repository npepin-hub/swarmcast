"""WC26 + WC-history MCP clients — replaces static RAG + live API data.

Two MCP servers:
  wc26-mcp             — WC2026 fixtures, teams, news, injuries, odds
  @zafronix/wc-mcp    — Historical WC data 1930-2026 (matches, rosters, brackets)

Each _call*() spins up the relevant npx server, sends initialize + tools/call
over stdin, and returns the text content.

Caching layers (fastest → slowest):
  1. In-memory  — 1h TTL (same process, hot path)
  2. Disk cache — mcp_disk_cache.json next to this file
                  * _call (live WC26):    24h TTL
                  * _call_history (historical): no expiry (immutable data)
  3. API call   — result saved to both layers; error responses are NOT cached
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import pathlib
import subprocess
import threading
import time
from ..config import settings

log = logging.getLogger(__name__)

_TTL = 3600           # in-memory TTL (seconds)
_LIVE_DISK_TTL = 86400  # disk TTL for live WC26 data (24h)
_cache: dict[str, tuple[float, str]] = {}

# ---------- disk cache -------------------------------------------------------

_DISK_CACHE_PATH = pathlib.Path(__file__).parent / "mcp_disk_cache.json"
_disk_cache: dict[str, dict] = {}   # key → {"ts": float, "text": str}
_disk_lock = threading.Lock()


def _load_disk_cache() -> None:
    with _disk_lock:
        global _disk_cache
        try:
            _disk_cache = json.loads(_DISK_CACHE_PATH.read_text())
            log.info("mcp disk cache loaded: %d entries", len(_disk_cache))
        except FileNotFoundError:
            _disk_cache = {}
        except Exception as exc:
            log.warning("mcp disk cache unreadable, starting fresh: %s", exc)
            _disk_cache = {}


def _flush_disk_cache() -> None:
    # Caller must already hold _disk_lock
    try:
        snapshot = dict(_disk_cache)
        _DISK_CACHE_PATH.write_text(json.dumps(snapshot, indent=2))
    except Exception as exc:
        log.warning("mcp disk cache write failed: %s", exc)


def _disk_put(key: str, text: str) -> None:
    """Store a successful (non-error) response and flush to disk."""
    if not text or text.startswith("Error:"):
        return
    with _disk_lock:
        _disk_cache[key] = {"ts": time.time(), "text": text}
        _flush_disk_cache()


def _disk_get(key: str, ttl: float | None) -> str | None:
    """Return cached text if present and within TTL (None = infinite)."""
    with _disk_lock:
        entry = _disk_cache.get(key)
    if not entry:
        return None
    if ttl is not None and time.time() - entry["ts"] > ttl:
        return None
    return entry["text"]


_load_disk_cache()

# ---------- MCP helpers ------------------------------------------------------


def _call(tool: str, params: dict) -> str:
    key = f"{tool}:{json.dumps(params, sort_keys=True)}"
    now = time.time()

    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]

    hit = _disk_get(key, _LIVE_DISK_TTL)
    if hit is not None:
        _cache[key] = (now, hit)
        return hit

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
    _disk_put(key, text)
    return text


def _call_history(tool: str, params: dict) -> str:
    """Call a @zafronix/wc-mcp tool (historical WC data 1930-2026)."""
    key = f"wc:{tool}:{json.dumps(params, sort_keys=True)}"
    now = time.time()

    if key in _cache and now - _cache[key][0] < _TTL:
        return _cache[key][1]

    # Historical data never changes — no TTL on disk
    hit = _disk_get(key, None)
    if hit is not None:
        _cache[key] = (now, hit)
        return hit

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
    _disk_put(key, text)
    return text


def _squad_context(profile_json: str, team: str) -> str:
    """Extract key players, injury status, and tournament odds from a team profile."""
    try:
        d = json.loads(profile_json)
    except Exception:
        return profile_json  # pass raw text if unparseable

    lines = [f"### {team}"]

    kp = d.get("key_players", [])
    if kp:
        lines.append("Key players (name · position · club):")
        for p in kp:
            lines.append(f"  - {p['name']} · {p.get('position','?')} · {p.get('club','?')}")

    injuries = d.get("injury_report", [])
    if injuries:
        lines.append("Injury report:")
        for inj in injuries:
            lines.append(f"  - {inj}")
    else:
        lines.append("No injury reports available (pre-tournament).")

    odds = d.get("tournament_odds", {})
    gp = odds.get("group_prediction", {})
    narrative = gp.get("narrative", "")
    if narrative:
        lines.append(f"Group outlook: {narrative}")

    dark_horse = odds.get("dark_horse_pick", "")
    if dark_horse:
        lines.append(f"Dark horse note: {dark_horse}")

    return "\n".join(lines)

# Public aliases for MCP tool invocations from specialist agents
call_wc26 = _call
call_wc_history = _call_history


def get_groups_data() -> dict:
    """Fetch all 12 WC 2026 groups with teams and matches. Cached for the session."""
    raw = _call("get_groups", {})
    try:
        return json.loads(raw)
    except Exception:
        return {"groups": []}


async def build_context_bundle(
    team_a: str,
    team_b: str,
    group: str = "",
) -> dict[str, str]:
    """Return context slices keyed by data_slice_id, sourced live from wc26-mcp.
    All 12 MCP calls run concurrently via asyncio.gather.
    get_injuries is omitted (empty pre-tournament); squad/fitness data is
    extracted directly from get_team_profile which carries key_players,
    injury_report, and tournament_odds fields.
    """
    (
        profile_a, profile_b, compare, h2h,
        hist_team_a, hist_team_b,
        matches_a, matches_b,
        news_a, news_b,
        standings, odds,
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
        asyncio.to_thread(_call, "get_standings",           {"group": group} if group else {}),
        asyncio.to_thread(_call, "get_odds",                {"category": "groups"}),
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
            f"## Scheduled Matches\n\n### {team_a}\n{matches_a}"
            f"\n\n### {team_b}\n{matches_b}"
            f"\n\n## Latest News\n\n### {team_a}\n{news_a}"
            f"\n\n### {team_b}\n{news_b}"
        ),
        "live_injuries": (
            f"## Squad & Fitness Context\n"
            f"NOTE: Official injury reports are pre-tournament and may be incomplete. "
            f"Use key player data, club affiliations, and group outlook as fitness proxies.\n\n"
            f"{_squad_context(profile_a, team_a)}\n\n"
            f"{_squad_context(profile_b, team_b)}"
        ),
        "live_standings": (
            f"## Group Standings\n{standings}"
            f"\n\n## Bookmaker Group Predictions\n{odds}"
        ),
    }
