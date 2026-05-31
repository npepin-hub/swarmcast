"""Weave-instrumented evaluation for SwarmCast — logs to W&B Evaluations tab.

Usage (standalone):
    python -m backend.eval.weave_eval

Or called from the router during the /history WebSocket run.
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


class SwarmCastPredictor(weave.Model):
    """Wraps the SwarmCast deliberation pipeline as a Weave Model."""

    model_name: str = "swarmcast-v1"
    # optional callback to stream intermediate results (used by the WS route)
    _emit: Any = None

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

        verdict = judge_prediction(
            result.consensus.probability,
            actual_winner,
            team_a,
            team_b,
            stage,
        )

        output = {
            "match_id":    match_id,
            "probability": result.consensus.probability,
            "ci_low":      result.consensus.ci_low,
            "ci_high":     result.consensus.ci_high,
            **verdict,
        }

        # Stream to WebSocket if a callback was attached
        if self._emit:
            await self._emit(output)

        return output


@weave.op
def score_correctness(actual_winner: str, output: dict) -> dict:
    """Weave scorer — did the agent pick the right winner?"""
    return {
        "correct":    output.get("correct", False),
        "confidence": output.get("confidence", 0.5),
    }


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
    ensure_init()

    matches = await asyncio.to_thread(sample_2022, seed)
    rows = _matches_to_rows(matches)

    dataset = weave.Dataset(name="wc2022-backtest", rows=rows)

    model = SwarmCastPredictor(model_name=f"swarmcast-seed{seed}")
    model._emit = emit

    evaluation = weave.Evaluation(
        name="wc2022-backtest",
        dataset=dataset,
        scorers=[score_correctness],
    )

    summary = await evaluation.evaluate(model)
    return summary


if __name__ == "__main__":
    result = asyncio.run(run_weave_evaluation())
    print("Evaluation complete:", result)
