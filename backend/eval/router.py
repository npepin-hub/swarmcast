"""FastAPI router for /history evaluation page."""
from __future__ import annotations
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .wc_backtest import sample_2022
from .weave_eval import run_weave_evaluation

router = APIRouter()


@router.get("/history")
async def history_page():
    return FileResponse("frontend/history.html")


@router.get("/history/matches")
async def history_matches(seed: int = 42):
    """Return the sampled match list without running evaluation."""
    matches = await asyncio.to_thread(sample_2022, seed)
    return [
        {
            "match_id": m.match_id, "team_a": m.team_a, "team_b": m.team_b,
            "stage": m.stage, "actual_winner": m.actual_winner,
            "score": m.score, "group": m.group,
        }
        for m in matches
    ]


@router.websocket("/history/ws")
async def history_ws(ws: WebSocket, seed: int = 42):
    await ws.accept()
    try:
        # Send match list upfront so the table renders immediately
        matches = await asyncio.to_thread(sample_2022, seed)
        await ws.send_json({"type": "matches", "data": [
            {"match_id": m.match_id, "team_a": m.team_a, "team_b": m.team_b,
             "stage": m.stage, "actual_winner": m.actual_winner,
             "score": m.score, "group": m.group}
            for m in matches
        ]})

        correct_total = 0
        evaluated = 0

        async def on_result(output: dict) -> None:
            nonlocal correct_total, evaluated
            evaluated += 1
            if output.get("correct"):
                correct_total += 1
            try:
                await ws.send_json({
                    "type": "result",
                    "accuracy_so_far": correct_total / evaluated,
                    "done": evaluated == len(matches),
                    **output,
                })
            except Exception:
                pass

        # Also notify browser when each match starts running
        original_emit = on_result
        running_set: set[str] = set()

        async def emit_with_start(output: dict) -> None:
            mid = output.get("match_id", "")
            if mid not in running_set:
                running_set.add(mid)
            await original_emit(output)

        # Run Weave evaluation — logs to W&B AND streams to browser via emit
        summary = await run_weave_evaluation(seed=seed, emit=emit_with_start)

        await ws.send_json({
            "type": "complete",
            "accuracy": correct_total / evaluated if evaluated else 0,
            "weave_summary": str(summary),
        })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "match_id": "", "message": str(exc)})
        except Exception:
            pass
