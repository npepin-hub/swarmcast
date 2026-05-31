"""FastAPI app — /forecast + WebSocket."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import weave
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.pipeline import run_deliberation
from .agents.delphi import synthesize_verdict
from .config import settings
from .data.wc26 import build_context_bundle, get_groups_data
from .market.edge import detect_and_act
from .market.gamma import (
    fetch_winner_odds,
    fetch_top_wc_favorites,
    get_match_markets,
    resolve_wc_moneyline_market,
)
from .observability import weave_tracer
from .schemas import ForecastResult, MarketSnapshot, WSEventType, WSMessage
from .eval.router import router as eval_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    weave_tracer.init()
    yield


app = FastAPI(title="SwarmCast", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="frontend"), name="static")
app.include_router(eval_router)


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, msg: WSMessage):
        for ws in list(self._connections):
            try:
                await ws.send_text(msg.model_dump_json())
            except Exception:
                self.disconnect(ws)


manager = ConnectionManager()


class ForecastRequest(BaseModel):
    match_query: str
    team_a: str
    team_b: str
    home_team_code: str = ""
    away_team_code: str = ""
    match_date: str = ""          # ISO date YYYY-MM-DD from bracket
    competition: str = ""         # e.g. "Group Stage · Group I"
    competition_id: str = ""      # group letter for standings MCP
    match_id: str = ""
    polymarket_market_id: str = ""


@weave.op()
def run_market_validation(
    consensus_probability: float,
    team_a: str,
    team_b: str,
    polymarket_market_id: str,
    match_date: str = "",
    home_team_code: str = "",
    away_team_code: str = "",
):
    """Resolve exact match moneyline via Gamma slug; fall back to winner-odds H2H."""
    market_id = ""
    event_slug = ""
    try:
        market_id, event_slug = resolve_wc_moneyline_market(
            team_a,
            team_b,
            polymarket_market_id=polymarket_market_id,
            match_date=match_date,
            home_team_code=home_team_code,
            away_team_code=away_team_code,
        )
        if market_id:
            snapshot, spread, edge_detected, bet_receipt = detect_and_act(
                consensus_probability, market_id
            )
            return snapshot, spread, edge_detected, bet_receipt, market_id, event_slug
    except Exception as exc:
        print(f"[market] match market skipped: {exc}")

    try:
        odds = fetch_winner_odds(team_a, team_b)
        p_a = odds.get(team_a)
        p_b = odds.get(team_b)
        if p_a and p_b:
            total = p_a.market_probability + p_b.market_probability
            if total > 0:
                h2h_p = p_a.market_probability / total
                spread = abs(consensus_probability - h2h_p)
                snapshot = MarketSnapshot(
                    market_id="winner_odds_derived",
                    market_probability=round(h2h_p, 4),
                    volume_24h=None,
                    open_interest=None,
                )
                edge_detected = spread > settings.edge_threshold
                return snapshot, spread, edge_detected, None, "winner_odds_derived", event_slug
    except Exception as exc:
        print(f"[market] winner odds fallback skipped: {exc}")

    return None, None, False, None, market_id, event_slug


@weave.op()
async def run_forecast_pipeline(req: ForecastRequest) -> ForecastResult:
    async def emit(event: WSEventType, payload):
        await manager.broadcast(WSMessage(event=event, payload=payload))

    trace_meta = {
        "match_id": req.match_id,
        "match_date": req.match_date,
        "competition": req.competition,
        "competition_id": req.competition_id,
        "home_team_code": req.home_team_code,
        "away_team_code": req.away_team_code,
    }
    with weave.attributes(trace_meta):
        return await _run_forecast_pipeline_inner(req, emit)


async def _run_forecast_pipeline_inner(
    req: ForecastRequest,
    emit,
) -> ForecastResult:
    contexts = await build_context_bundle(req.team_a, req.team_b, req.competition_id)
    result = await run_deliberation(
        req.match_query,
        req.team_a,
        req.team_b,
        contexts,
        emit=emit,
        group=req.competition_id,
        match_date=req.match_date,
        competition=req.competition,
    )

    forecast = ForecastResult(
        match_query=req.match_query,
        consensus=result.consensus,
        critique=result.critique,
        market=None,
        spread=None,
        edge_detected=False,
        bet_receipt=None,
    )

    # Verdict — narrative synthesis of round-2 votes
    verdict = await synthesize_verdict(
        req.match_query, result.consensus, result.consensus.all_votes,
        req.team_a, req.team_b,
    )
    await emit(WSEventType.verdict, {"text": verdict})

    # Polymarket — 3-way match markets (win/draw/lose) if match date is known
    if req.match_date:
        match_mkts = await asyncio.to_thread(
            get_match_markets, req.team_a, req.team_b, req.match_date
        )
        if match_mkts:
            await emit(WSEventType.match_markets, match_mkts.model_dump())

    # Polymarket — tournament winner odds + derived H2H + top favorites
    winner_odds = await asyncio.to_thread(fetch_winner_odds, req.team_a, req.team_b)
    top_favorites = await asyncio.to_thread(fetch_top_wc_favorites, 5)
    if winner_odds:
        odds_a = winner_odds.get(req.team_a)
        odds_b = winner_odds.get(req.team_b)
        h2h = None
        if odds_a and odds_b:
            total = odds_a.market_probability + odds_b.market_probability
            if total > 0:
                h2h = {
                    req.team_a: round(odds_a.market_probability / total, 4),
                    req.team_b: round(odds_b.market_probability / total, 4),
                }
        await emit(WSEventType.winner_odds, {
            "teams":     {team: snap.model_dump() for team, snap in winner_odds.items()},
            "h2h":       h2h,
            "favorites": top_favorites,
        })

    snapshot, spread, edge_detected, bet_receipt, market_id, event_slug = (
        await asyncio.to_thread(
            run_market_validation,
            forecast.consensus.probability,
            req.team_a,
            req.team_b,
            req.polymarket_market_id,
            req.match_date,
            req.home_team_code,
            req.away_team_code,
        )
    )
    await emit(WSEventType.market_check, {
        "snapshot": snapshot.model_dump() if snapshot else None,
        "spread": spread,
        "market_id": market_id,
        "event_slug": event_slug,
    })
    await emit(WSEventType.edge_result, {
        "edge_detected": edge_detected,
        "bet_receipt": bet_receipt.model_dump() if bet_receipt else None,
    })

    forecast.market = snapshot
    forecast.spread = spread
    forecast.edge_detected = edge_detected
    forecast.bet_receipt = bet_receipt
    return forecast


async def run_pipeline(req: ForecastRequest) -> ForecastResult:
    return await run_forecast_pipeline(req)


@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


@app.get("/matches")
async def matches():
    """Return all WC 2026 groups with teams and matches — used by the bracket UI."""
    return await asyncio.to_thread(get_groups_data)


@app.get("/health")
async def health():
    return {"status": "ok", "weave_project": settings.weave_project_path}


@app.post("/forecast", response_model=ForecastResult)
async def forecast(req: ForecastRequest):
    return await run_pipeline(req)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
