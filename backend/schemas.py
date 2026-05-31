from __future__ import annotations
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


# ── Agent layer ──────────────────────────────────────────────────────────────

class SpecialistDefinition(BaseModel):
    role: str
    system_prompt: str
    data_slice_id: str
    focus: str = ""   # short descriptor shown in the fish speech bubble


class AgentVote(BaseModel):
    role: str
    team_a_goals: int = Field(ge=0, le=20, description="Predicted goals for team A")
    team_b_goals: int = Field(ge=0, le=20, description="Predicted goals for team B")
    probability: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    key_signal: str
    reasoning: str
    uncertainty_flag: bool
    round: int = 1  # 1 = first vote, 2 = post-Delphi


# ── Critic layer ─────────────────────────────────────────────────────────────

class CriticAction(str, Enum):
    spawn = "spawn"
    rewrite = "rewrite"
    broadcast = "broadcast"


class RecommendedAction(BaseModel):
    action: CriticAction
    rationale: str
    target_role: str | None = None  # for rewrite; None = broadcast to all


class CritiqueOutput(BaseModel):
    coverage_gaps: list[str]
    groupthink_signals: list[str]
    recommended_actions: list[RecommendedAction]


# ── Delphi / consensus layer ──────────────────────────────────────────────────

class ConsensusResult(BaseModel):
    team_a_goals: float
    team_b_goals: float
    probability: float = Field(ge=0.0, le=1.0)
    ci_low: float
    ci_high: float
    minority_dissent: list[AgentVote]   # votes > 1 std-dev from consensus
    all_votes: list[AgentVote]


# ── Market / edge layer ───────────────────────────────────────────────────────

class MarketSnapshot(BaseModel):
    market_id: str
    market_probability: float
    volume_24h: float | None = None
    open_interest: float | None = None


class BetReceipt(BaseModel):
    order_id: str
    market_id: str
    side: str
    size: float
    price: float
    status: str


# ── Pipeline output ───────────────────────────────────────────────────────────

class ForecastResult(BaseModel):
    match_query: str
    consensus: ConsensusResult
    critique: CritiqueOutput
    market: MarketSnapshot | None
    spread: float | None
    edge_detected: bool
    bet_receipt: BetReceipt | None


# ── WebSocket messages ────────────────────────────────────────────────────────

class WSEventType(str, Enum):
    spawning = "spawning"           # orchestrator writing specialist definitions
    agent_vote = "agent_vote"       # one specialist has voted
    critic_fired = "critic_fired"   # holistic critic output ready
    delphi_round = "delphi_round"   # round 2 votes incoming
    consensus = "consensus"         # final consensus locked
    verdict = "verdict"             # narrative synthesis of round-2 votes
    match_markets = "match_markets" # polymarket 3-way match odds (win/draw/lose)
    winner_odds = "winner_odds"     # polymarket tournament winner odds for both teams
    market_check = "market_check"   # polymarket snapshot fetched
    edge_result = "edge_result"     # spread computed, bet decision made
    error = "error"


class WSMessage(BaseModel):
    event: WSEventType
    payload: Any
