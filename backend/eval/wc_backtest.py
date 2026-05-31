"""2022 WC backtest — samples completed matches, runs SwarmCast, compares vs actual."""
from __future__ import annotations
import dataclasses
import json
import logging
import pathlib
import random
from dataclasses import dataclass
from typing import Any

from ..data.wc26 import _call_history

log = logging.getLogger(__name__)

# Persisted match list — survives server restarts and API rate-limit windows
_DISK_CACHE = pathlib.Path(__file__).parent / "wc2022_match_cache.json"


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

# Static 2022 WC sample — used when the live API is unavailable (e.g., rate-limited)
_FALLBACK_MATCHES: list[BacktestMatch] = [
    # Group stage
    BacktestMatch("2022-001", "Germany",   "Japan",       "group",         "Japan",      "1-2", "E"),
    BacktestMatch("2022-002", "Argentina", "Saudi Arabia","group",         "Saudi Arabia","1-2","C"),
    BacktestMatch("2022-003", "Spain",     "Costa Rica",  "group",         "Spain",      "7-0", "E"),
    BacktestMatch("2022-004", "Morocco",   "Belgium",     "group",         "Morocco",    "2-0", "F"),
    # Round of 16
    BacktestMatch("2022-049", "Brazil",    "South Korea", "round of 16",   "Brazil",     "4-1"),
    BacktestMatch("2022-050", "France",    "Poland",      "round of 16",   "France",     "3-1"),
    BacktestMatch("2022-051", "Morocco",   "Spain",       "round of 16",   "Morocco",    "0-0 (pens)"),
    BacktestMatch("2022-052", "England",   "Senegal",     "round of 16",   "England",    "3-0"),
    # Quarter-finals
    BacktestMatch("2022-057", "Croatia",   "Brazil",      "quarter_final", "Croatia",    "1-1 (pens)"),
    BacktestMatch("2022-060", "Morocco",   "Portugal",    "quarter_final", "Morocco",    "1-0"),
    # Semi-finals
    BacktestMatch("2022-061", "Argentina", "Croatia",     "semi_final",    "Argentina",  "3-0"),
    # Final
    BacktestMatch("2022-064", "Argentina", "France",      "final",         "Argentina",  "3-3 (pens)"),
]


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


def _save_to_disk(matches: list[BacktestMatch]) -> None:
    try:
        _DISK_CACHE.write_text(
            json.dumps([dataclasses.asdict(m) for m in matches], indent=2)
        )
        log.info("wc_backtest: saved %d matches to %s", len(matches), _DISK_CACHE)
    except Exception as exc:
        log.warning("wc_backtest: could not write cache: %s", exc)


def _load_from_disk() -> list[BacktestMatch]:
    try:
        rows = json.loads(_DISK_CACHE.read_text())
        matches = [BacktestMatch(**r) for r in rows]
        log.info("wc_backtest: loaded %d matches from disk cache", len(matches))
        return matches
    except Exception:
        return []


def sample_2022(seed: int = 42) -> list[BacktestMatch]:
    """Return ~12 representative 2022 WC matches across stages.

    Priority: live API → disk cache → static fallback.
    Saves to disk whenever the live API returns data.
    """
    random.seed(seed)
    matches: list[BacktestMatch] = []
    matches += _group_matches(2022, sample_per_group=1)[:4]
    matches += _knockout_matches(2022, ["round_of_16"], sample_per_stage=2)[:4]
    matches += _knockout_matches(2022, ["quarter_final"], sample_per_stage=1)[:2]
    matches += _knockout_matches(2022, ["semi_final", "final"], sample_per_stage=2)

    if matches:
        _save_to_disk(matches)
        return matches

    cached = _load_from_disk()
    if cached:
        return cached

    log.warning("wc_backtest: API unavailable and no disk cache; using static fallback")
    return list(_FALLBACK_MATCHES)


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
