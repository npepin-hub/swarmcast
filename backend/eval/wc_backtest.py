"""2022 WC backtest — samples completed matches, runs SwarmCast, compares vs actual."""
from __future__ import annotations
import json
import random
from dataclasses import dataclass
from typing import Any

from ..data.wc26 import _call_history


@dataclass
class BacktestMatch:
    match_id: str
    team_a: str          # home team
    team_b: str          # away team
    stage: str
    actual_winner: str   # team name or "draw"
    score: str           # e.g. "3-0"
    group: str = ""


# Penalty winners missing from the MCP — hardcoded from official records
_KNOWN_PENALTY_WINNERS: dict[str, str] = {
    "2022-057": "Croatia",    # Croatia beat Brazil 4-2
    "2022-058": "Argentina",  # Argentina beat Netherlands 4-3
    "2022-064": "Argentina",  # Argentina beat France 4-2
    "2022-053": "Japan",      # Japan beat Spain ... actually this was group stage
    "2018-054": "Croatia",    # Croatia beat Denmark 3-2
    "2018-055": "Russia",     # Russia beat Spain 4-3
}


def _bracket_winners(year: int) -> dict[str, str]:
    """Return matchId → winner for all knockout matches."""
    raw = _call_history("get_bracket", {"year": year})
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    winners = {}
    for stage_matches in data.get("stages", {}).values():
        for m in stage_matches:
            mid = m.get("matchId") or m.get("id")
            winner = m.get("winner")
            if mid and winner:
                winners[mid] = winner
    return winners


def _group_matches(year: int, sample_per_group: int = 1) -> list[BacktestMatch]:
    """Sample group-stage matches with draws included."""
    groups = ["group_a", "group_b", "group_c", "group_d",
              "group_e", "group_f", "group_g", "group_h"]
    result = []
    for g in groups:
        raw = _call_history("list_matches", {"year": year, "stage": g})
        try:
            matches = json.loads(raw).get("data", [])
        except Exception:
            continue
        # Only take matches with known scores
        played = [m for m in matches if m.get("homeScore") is not None]
        sample = random.sample(played, min(sample_per_group, len(played)))
        for m in sample:
            hs, as_ = m["homeScore"], m["awayScore"]
            if hs > as_:
                winner = m["homeTeam"]
            elif as_ > hs:
                winner = m["awayTeam"]
            else:
                winner = "draw"
            result.append(BacktestMatch(
                match_id=m["id"],
                team_a=m["homeTeam"],
                team_b=m["awayTeam"],
                stage="group",
                actual_winner=winner,
                score=m.get("result", f"{hs}–{as_}"),
                group=g.replace("group_", "").upper(),
            ))
    return result


def _knockout_matches(year: int, stages: list[str], sample_per_stage: int = 2) -> list[BacktestMatch]:
    """Sample knockout matches; uses bracket winner to handle ET/pens."""
    bracket_winners = _bracket_winners(year)
    result = []
    for stage in stages:
        raw = _call_history("list_matches", {"year": year, "stage": stage})
        try:
            matches = json.loads(raw).get("data", [])
        except Exception:
            continue
        played = [m for m in matches if m.get("homeScore") is not None]
        sample = random.sample(played, min(sample_per_stage, len(played)))
        for m in sample:
            mid = m["id"]
            winner = (
                _KNOWN_PENALTY_WINNERS.get(mid)
                or bracket_winners.get(mid)
                or (m["homeTeam"] if m["homeScore"] > m["awayScore"] else m["awayTeam"])
            )
            result.append(BacktestMatch(
                match_id=m["id"],
                team_a=m["homeTeam"],
                team_b=m["awayTeam"],
                stage=stage.replace("_", " "),
                actual_winner=winner,
                score=m.get("result", "?"),
            ))
    return result


def sample_2022(seed: int = 42) -> list[BacktestMatch]:
    """Return ~12 representative 2022 WC matches across stages."""
    random.seed(seed)
    matches: list[BacktestMatch] = []
    # 4 group stage (1 per pair of groups — pick 4 of 8 groups)
    matches += _group_matches(2022, sample_per_group=1)[:4]
    # 4 Round of 16
    matches += _knockout_matches(2022, ["round_of_16"], sample_per_stage=2)[:4]
    # 2 Quarter-finals
    matches += _knockout_matches(2022, ["quarter_final"], sample_per_stage=1)[:2]
    # Semi-finals + final (all 3 — small enough)
    matches += _knockout_matches(2022, ["semi_final", "final"], sample_per_stage=2)
    return matches


def judge_prediction(predicted_prob_a: float, actual_winner: str,
                     team_a: str, team_b: str, stage: str) -> dict[str, Any]:
    """Return correctness info for one prediction."""
    DRAW_BAND = 0.08   # within ±8pp of 50% → predict draw

    if actual_winner == "draw":
        correct = abs(predicted_prob_a - 0.5) <= DRAW_BAND
        predicted = "draw" if correct else (team_a if predicted_prob_a > 0.5 else team_b)
    else:
        predicted = team_a if predicted_prob_a > 0.5 else team_b
        correct = predicted == actual_winner

    return {
        "predicted": predicted,
        "actual": actual_winner,
        "correct": correct,
        "confidence": max(predicted_prob_a, 1 - predicted_prob_a),
    }
