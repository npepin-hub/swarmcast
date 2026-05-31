"""Weave-instrumented evaluation for SwarmCast — logs to W&B Evaluations tab.

Live WC2026 forecasts: deliberation only (no winner scoring until results exist).
Post-game: set ENABLE_MATCH_SCORING=true and run /history or weave_eval on completed matches.

Optional LLM judge: ENABLE_WEAVE_JUDGE=true + WEAVE_JUDGE_REF=Judge:v0 (criteria live in that object).

Usage (standalone):
    python -m backend.eval.weave_eval
"""
from __future__ import annotations
import asyncio
from collections.abc import Callable, Awaitable
from typing import Any

import weave

from ..agents.pipeline import run_deliberation
from ..config import settings
from ..data.wc26 import build_context_bundle
from ..observability.weave_tracer import ensure_init
from .wc_backtest import BacktestMatch, judge_prediction, sample_2022


# Module-level emit callback — avoids Weave model serialization dropping instance attrs
_active_emit: Callable[[dict], Awaitable[None]] | None = None


class SwarmCastPredictor(weave.Model):
    """Wraps the SwarmCast deliberation pipeline as a Weave Model."""

    model_name: str = "swarmcast-v1"

    @weave.op
    async def predict(
        self,
        match_id: str,
        team_a: str,
        team_b: str,
        stage: str,
        group: str,
        actual_winner: str,
    ) -> dict:
        match_query = (
            f"Who wins {team_a} vs {team_b}? "
            f"Provide win probability for {team_a} and confidence."
        )
        contexts = await build_context_bundle(team_a, team_b, group)
        result = await run_deliberation(match_query, team_a, team_b, contexts, emit=None)

        output = {
            "match_id": match_id,
            "probability": result.consensus.probability,
            "ci_low": result.consensus.ci_low,
            "ci_high": result.consensus.ci_high,
            "judging_status": "deferred",
        }
        if settings.enable_match_scoring and actual_winner:
            output.update(
                judge_prediction(
                    result.consensus.probability,
                    actual_winner,
                    team_a,
                    team_b,
                    stage,
                )
            )
            output["judging_status"] = "scored"

        if _active_emit:
            await _active_emit(output)

        return output


@weave.op
def score_correctness(actual_winner: str, output: dict) -> dict:
    """Weave scorer — did the agent pick the right winner?"""
    return {
        "correct": output.get("correct", False),
        "confidence": output.get("confidence", 0.5),
    }


def load_evaluation_scorers() -> list:
    """Scorers for weave.Evaluation — only when post-game scoring is enabled."""
    if not settings.enable_match_scoring:
        return []
    scorers: list = [score_correctness]
    if not settings.enable_weave_judge:
        return scorers
    ref = (settings.weave_judge_ref or "").strip()
    if not ref:
        return scorers
    try:
        judge = weave.ref(ref).get()
        scorers.insert(0, judge)
        print(f"[eval] Using Weave judge: {ref}")
    except Exception as exc:
        print(f"[eval] weave_judge_ref {ref!r} unavailable ({exc}); using score_correctness only")
    return scorers


def _matches_to_rows(matches: list[BacktestMatch]) -> list[dict]:
    return [
        {
            "match_id":      m.match_id,
            "team_a":        m.team_a,
            "team_b":        m.team_b,
            "stage":         m.stage,
            "group":         m.group,
            "actual_winner": m.actual_winner,
            "score":         m.score,
        }
        for m in matches
    ]


async def run_weave_evaluation(
    seed: int = 42,
    emit: Callable[[dict], Awaitable[None]] | None = None,
) -> dict:
    """Run the full evaluation, log to Weave, return summary metrics.

    `emit` is an optional async callback called after each match completes —
    used by the WebSocket route to stream results to the browser.
    """
    global _active_emit
    ensure_init()

    matches = await asyncio.to_thread(sample_2022, seed)
    rows = _matches_to_rows(matches)

    dataset = weave.Dataset(name="wc2022-backtest", rows=rows)
    model = SwarmCastPredictor(model_name=f"swarmcast-seed{seed}")

    evaluation = weave.Evaluation(
        name="wc2022-backtest",
        dataset=dataset,
        scorers=load_evaluation_scorers(),
    )

    _active_emit = emit
    try:
        summary = await evaluation.evaluate(model)
    finally:
        _active_emit = None

    return summary


if __name__ == "__main__":
    result = asyncio.run(run_weave_evaluation())
    print("Evaluation complete:", result)
