"""Build train.csv-compatible feature rows from MCP (+ CSV fallback)."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from ...data.mcp_registry import invoke_tool
from .wc_model import INDEPENDENT_VARS, TRAIN_CSV


def _try_parse_json(text: str) -> object | None:
    text = (text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    return None


def _normalize_team(name: str) -> str:
    return re.sub(r"\s+", " ", name.strip().lower())


def _csv_fallback_row(team: str) -> dict:
    df = pd.read_csv(TRAIN_CSV)
    norm = _normalize_team(team)
    df["_norm"] = df["team"].astype(str).map(_normalize_team)
    rows = df[df["_norm"] == norm]
    if rows.empty:
        rows = df[df["team"].astype(str).str.contains(team, case=False, na=False)]
    if rows.empty:
        medians = {col: float(df[col].median()) for col in INDEPENDENT_VARS}
        return {"team": team, **medians, "_source": "csv_median"}
    row = rows.iloc[-1]
    return {
        "team": team,
        **{col: float(row[col]) for col in INDEPENDENT_VARS},
        "_source": "csv_latest",
    }


def _extract_from_matches_payload(payload: object) -> dict | None:
    """Aggregate goals and W/D/L from wc26_get_matches JSON."""
    if payload is None:
        return None
    matches: list = []
    if isinstance(payload, list):
        matches = payload
    elif isinstance(payload, dict):
        for key in ("matches", "fixtures", "results", "data"):
            if key in payload and isinstance(payload[key], list):
                matches = payload[key]
                break
        if not matches and "team" in payload:
            matches = [payload]

    scored = received = wins = losses = draws = 0
    counted = 0
    for m in matches:
        if not isinstance(m, dict):
            continue
        status = str(m.get("status", "")).lower()
        if status and status not in ("finished", "completed", "ft", "final"):
            continue
        home = m.get("home_team") or m.get("home") or {}
        away = m.get("away_team") or m.get("away") or {}
        if isinstance(home, str):
            home_goals = m.get("home_goals") or m.get("home_score")
            away_goals = m.get("away_goals") or m.get("away_score")
        else:
            home_goals = home.get("goals") or home.get("score") or m.get("home_goals")
            away_goals = away.get("goals") or away.get("score") or m.get("away_goals")
        if home_goals is None or away_goals is None:
            score = m.get("score") or m.get("result")
            if isinstance(score, str) and "-" in score:
                parts = re.findall(r"\d+", score)
                if len(parts) >= 2:
                    home_goals, away_goals = int(parts[0]), int(parts[1])
        if home_goals is None or away_goals is None:
            continue
        hg, ag = int(home_goals), int(away_goals)
        team_side = str(m.get("team_side", "")).lower()
        is_home = team_side == "home" or m.get("is_home") is True
        if is_home:
            scored += hg
            received += ag
            if hg > ag:
                wins += 1
            elif hg < ag:
                losses += 1
            else:
                draws += 1
        else:
            scored += ag
            received += hg
            if ag > hg:
                wins += 1
            elif ag < hg:
                losses += 1
            else:
                draws += 1
        counted += 1

    if counted == 0:
        return None
    return {
        "goals_scored_last_4y": scored,
        "goals_received_last_4y": received,
        "wins_last_4y": wins,
        "losses_last_4y": losses,
        "draws_last_4y": draws,
        "_source": "mcp_matches",
        "_match_count": counted,
    }


def _extract_from_history(payload: object) -> dict | None:
    """Use history_get_team aggregates when match list is empty."""
    if not isinstance(payload, dict):
        return None
    stats = payload.get("stats") or payload.get("statistics") or payload
    if not isinstance(stats, dict):
        return None
    scored = stats.get("goals_scored") or stats.get("goals_for") or stats.get("total_goals")
    received = stats.get("goals_conceded") or stats.get("goals_against") or stats.get("goals_received")
    wins = stats.get("wins") or stats.get("win")
    losses = stats.get("losses") or stats.get("loss")
    draws = stats.get("draws") or stats.get("draw")
    if scored is None and received is None:
        return None
    return {
        "goals_scored_last_4y": int(scored or 0),
        "goals_received_last_4y": int(received or 0),
        "wins_last_4y": int(wins or 0),
        "losses_last_4y": int(losses or 0),
        "draws_last_4y": int(draws or 0),
        "_source": "mcp_history",
    }


def _fetch_team_features(team: str, opponent: str, *, use_mcp: bool) -> dict:
    if not use_mcp:
        return _csv_fallback_row(team)

    matches_raw = invoke_tool("wc26_get_matches", {"team": team})
    parsed = _try_parse_json(matches_raw)
    feats = _extract_from_matches_payload(parsed)
    if feats is None:
        hist_raw = invoke_tool("history_get_team", {"name": team})
        feats = _extract_from_history(_try_parse_json(hist_raw))
    if feats is None:
        fallback = _csv_fallback_row(team)
        fallback["_source"] = "csv_fallback"
        return fallback

    row = {"team": team, **{k: feats[k] for k in INDEPENDENT_VARS}}
    row["_source"] = feats.get("_source", "mcp")
    if "_match_count" in feats:
        row["_match_count"] = feats["_match_count"]
    return row


def build_match_features(
    team_a: str,
    team_b: str,
    *,
    use_mcp: bool = True,
) -> tuple[pd.DataFrame, dict]:
    """
    Return (feature_df, provenance) for predict_match.

    provenance maps team -> source metadata.
    """
    row_a = _fetch_team_features(team_a, team_b, use_mcp=use_mcp)
    row_b = _fetch_team_features(team_b, team_a, use_mcp=use_mcp)

    if use_mcp:
        invoke_tool(
            "wc26_compare_teams", {"team_a": team_a, "team_b": team_b}
        )

    provenance = {
        team_a: {k: v for k, v in row_a.items() if k.startswith("_") or k == "team"},
        team_b: {k: v for k, v in row_b.items() if k.startswith("_") or k == "team"},
    }
    df = pd.DataFrame(
        [
            {k: row_a[k] for k in ["team", *INDEPENDENT_VARS]},
            {k: row_b[k] for k in ["team", *INDEPENDENT_VARS]},
        ]
    )
    return df, provenance
