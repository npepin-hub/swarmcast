# SwarmCast
### A Self-Improving Multi-Agent Swarm for World Cup Match Forecasting
*with Polymarket Edge Detection and Automated Bet Placement*

> "Feed it a World Cup match. A swarm of specialist agents deliberates in isolation, a self-improving critic rewrites the swarm in real time, and emergent consensus appears — visualized as a school of fish finding direction."

*Multi-Agent Orchestration Hackathon · MIT / The Engine, Cambridge MA · May 31, 2026 · #BosTechWeek*

---

## 1. The Core Idea

SwarmCast is a multi-agent deliberation system for World Cup 2026 match forecasting. A meta-orchestrator reads a match question and dynamically spawns a pool of 8 specialist agents — each with a narrow analytical lens, a named focus area, and access to live MCP data. Agents deliberate in parallel in full isolation. A holistic critic reads the full panel and identifies what the collective intelligence is missing. A LangGraph-powered Delphi round gives each specialist one revision pass via its own agent thread. A confidence-weighted consensus probability emerges.

The consensus is compared to Polymarket — either a live match market or a head-to-head probability derived from tournament winner markets. If the spread exceeds 8 percentage points, SwarmCast places a limit order.

Every call is traced in W&B Weave. Resolved matches become training samples for v2.

### Why This Is Interesting

- **Genuine multi-agent orchestration** — 8 specialist agents with distinct roles, running in parallel via `asyncio.gather`. Not a single model with tools.
- **LangGraph Swarm for Delphi** — round 2 runs each specialist in its own LangGraph ReAct agent thread, preventing context blowup and enabling true per-agent deliberation.
- **MCP tools baked into agents** — specialists call wc26-mcp and @zafronix/wc-mcp directly as LangChain tools. Agents actively fetch their own data rather than receiving pre-injected context.
- **Self-improving critic loop** — the critic identifies coverage gaps and groupthink, the orchestrator spawns new agents or rewrites prompts, the swarm improves.
- **Falsifiable claim** — the output is a predicted score, a probability, a confidence interval, a minority dissent report, and an explicit spread against Polymarket. Verifiable in June.
- **Polymarket always shows** — pre-tournament, winner market odds (live $517M) are converted to head-to-head probability so the comparison is never empty.

---

## 2. System Architecture

### 2.1 Pipeline

```
match_query + team_a + team_b
        │
        ▼
[MCP Context]  wc26-mcp + @zafronix/wc-mcp — 13 parallel calls via asyncio.gather
        │
        ▼
[Meta-Orchestrator]  Qwen3-14B via W&B Inference
  → writes 8 specialist definitions (role, focus, system_prompt, data_slice_id)
        │
        ▼
[Specialist Swarm — Round 1]  asyncio.gather, full isolation
  → each agent: ReAct loop with MCP tools + inference_chat
  → output: { team_a_goals, team_b_goals, probability, confidence, key_signal, reasoning }
        │
        ▼
[Holistic Critic]  reads full panel as one document
  → returns: coverage_gaps, groupthink_signals, recommended_actions
        │
        ▼
[Orchestrator acts]  spawn / rewrite / broadcast
        │
        ▼
[Delphi Round 2]  LangGraph Swarm — one ReAct agent thread per specialist
  → agents see aggregate P distribution only (no reasoning chains)
  → each submits a revised vote
        │
        ▼
[Consensus]  confidence-weighted P + 80% CI + minority dissent
        │
        ▼
[Polymarket Validation]  first and only contact with Polymarket
  → match market if available; falls back to winner-odds H2H
  → edge = |SwarmCast P − market P|; if > 8pp → CLOB limit order
        │
        ▼
[Output]  consensus tile + VS Polymarket + agent aggregate table
```

### 2.2 Inference Layer

All LLM calls go through W&B Inference (CoreWeave-backed GPU infrastructure) via an OpenAI-compatible endpoint. Model: `OpenPipe/Qwen3-14B-Instruct` for all roles (orchestrator, specialists, critic, Delphi). Configured in `backend/agents/inference.py` using the `openai` Python SDK pointed at `https://api.inference.wandb.ai/v1`.

### 2.3 Specialist Agent Pool (8 agents)

| Role | Focus | What they analyze |
|---|---|---|
| tactical_analyst | xG · formations · pressing | xG, formation, pressing systems, structural tactical advantages |
| historical_stats | WC history · H2H · base rates | H2H records, WC tournament base rates, confederation matchup history |
| current_form | last 5 results · momentum · goals | Recent results, goals scored/conceded, trajectory |
| squad_fitness | injuries · suspensions · depth | Injury lists, suspensions, squad depth vs full-strength |
| tournament_context | standings · incentives · venue | Group standings, qualification scenarios, rest days, venue, strategic incentives |
| set_piece_specialist | corners · free kicks · dead ball | Set piece attacking/defensive record, key delivery and target players |
| psychological_analyst | big game record · pressure · experience | High-pressure record, average caps, big-game history, mental resilience |
| contrarian | underdog case · upset risk | Structurally biased against the favourite. Surfaces the strongest upset mechanism. |

The orchestrator aims for 7–9 specialists and may spawn additional agents based on critic recommendations. Each definition includes a `focus` field displayed in the fish speech bubble and the final aggregate table.

### 2.4 Delphi — LangGraph Swarm

Round 2 is implemented in `backend/agents/swarm_langgraph.py` using `langgraph-swarm`. Each specialist runs as a separate `create_react_agent` node. The orchestrator agent hands off to each specialist in sequence; each specialist sees only the aggregate probability distribution from round 1 (no reasoning chains) and submits a revised vote. This prevents context blowup across agents and enables genuine per-agent deliberation.

### 2.5 MCP Tool Integration

Specialists call live data as LangChain tools defined in `backend/agents/mcp_tools.py`. Tools are bound at agent spawn time based on `data_slice_id`. The MCP registry (`backend/data/mcp_registry.py`) maps tool names to the appropriate MCP subprocess call (wc26-mcp or @zafronix/wc-mcp).

---

## 3. Data Sources

> **Critical constraint:** No source publishing betting odds, prediction market prices, or bookmaker lines is permitted in the deliberation layer.

### Live — MCP servers

| MCP Server | npm package | Provides |
|---|---|---|
| wc26-mcp | `wc26-mcp` | WC 2026 fixtures, team profiles, form, injuries, standings, H2H, news |
| WC History MCP | `@zafronix/wc-mcp` | Historical WC data 1930–2026: matches, rosters, brackets, standings |

Both servers are invoked via `npx -y <package>` over MCP protocol (JSON-RPC over stdin). Results are cached in-process for 1 hour. No static corpus. No embedding step.

### Validation only — fetched after vote is sealed

| Source | Provides | Role |
|---|---|---|
| Polymarket Gamma API (no auth) | Match market implied P (when available) | Primary edge detector |
| Polymarket winner markets | Tournament winner P per team → derived H2H | Fallback (pre-tournament) |
| Polymarket CLOB API (wallet auth) | Order placement if spread > 8pp | Bet executor (stubbed) |

---

## 4. Tech Stack

| Component | Choice |
|---|---|
| Python | 3.11 |
| LLM inference | W&B Inference (CoreWeave GPU) — OpenAI-compatible endpoint |
| Model | `OpenPipe/Qwen3-14B-Instruct` (all roles) |
| Agent orchestration | `asyncio.gather` (round 1) + LangGraph Swarm (round 2 Delphi) |
| MCP integration | LangChain tools wrapping subprocess MCP calls |
| Observability | W&B Weave — `@weave.op()` on all agent functions |
| Live data | `wc26-mcp` + `@zafronix/wc-mcp` via npx |
| Backend | FastAPI + WebSockets |
| Frontend | Vanilla JS + p5.js |
| Visualization | p5.js Boids — 25 fish per specialist school, centroid speech bubbles |
| Polymarket | Gamma API (read) + winner markets (H2H fallback) + CLOB (stubbed) |

### Python dependencies

```
fastapi, uvicorn, websockets, httpx, pydantic, pydantic-settings
wandb, weave
langgraph-swarm, langgraph, langchain-openai, langchain-core
openai (pointed at W&B Inference endpoint)
python-dotenv
```

---

## 5. Context Engineering

- **Narrow role + focus** — each specialist prompt defines its role and focus explicitly. Scope enforcement prevents any agent from solving the whole problem.
- **MCP tools as the data layer** — specialists fetch their own data via bound LangChain tools. No pre-injected blobs.
- **Independence instruction** — every prompt: *"Form your own independent view based solely on your assigned data. Do not speculate about what other analysts might conclude."*
- **Market blindness** — no agent prompt references Polymarket, betting odds, or market-implied probability. Enforced at prompt construction level.
- **Sparse Delphi signal** — agents see only the aggregate P distribution in round 2 (no reasoning chains). Prevents anchoring, preserves pool diversity.
- **Focus field** — each specialist definition carries a short `focus` descriptor shown in the fish speech bubble and the final aggregate table.

---

## 6. UI — What Was Built

### Match Picker
- 12 WC 2026 group tiles (6×2 grid), loaded live from wc26-mcp at startup
- Each tile: group letter, 4 teams with flag emojis, 6 scheduled match rows
- Click any match row to select
- Knockout bracket collapsible below

### Question Picker
Five question cards (always visible, above the bracket):

| Card | Prompt |
|---|---|
| Who wins? | Win probability + confidence |
| Predict the final score | Goals per team + confidence |
| Who scores first? | First goal probability |
| Both teams to score? | BTTS probability |
| Over 2.5 goals? | Total goals market |

### Fish Visualization (p5.js Boids)
- **25 fish per specialist school** — 200 fish total for 8 agents
- Each school has its own colour (fixed palette, no purple)
- Per-fish randomisation: speed (3.5–6.0), turn rate (0.12–0.24), hue drift (±12°), size (0.7×–1.4×), sinusoidal wander offset
- One speech bubble per school at group centroid: role name + focus descriptor
- Phase transitions driven by WebSocket events:

| Phase | Fish behaviour |
|---|---|
| idle | Slow drift |
| deliberating | High chaos, fragmented schools |
| critic | Turbulence spike |
| delphi | Partial alignment emerging |
| consensus | Full lock, schools converge |

### Consensus Tile (result after pipeline completes)

```
PREDICTED SCORE
South Africa  1–2  South Korea
─────────────────────────────────────────
OUR PREDICTION      VS      POLYMARKET (H2H)
    37.7%                       16.7%
P(S.Africa wins)            market implied   │ EDGE
                                             │ 21.0pp
                                             │ bet placed
─────────────────────────────────────────────────────
Plain English explanation + 80% CI + dissent count
```

Hover tooltip on Edge badge explains: `Edge = |SwarmCast − Polymarket|`, threshold, action taken.

### Aggregate Table (appears at consensus)
Agent | Round 1 | Round 2 | Key signal | Reasoning
— with Focus shown under each agent name in the Agent column, and delta (±pp) between rounds.

---

## 7. Demo Script — 3 Minutes

**0:00 — Hook (15s)**
*"Polymarket gives South Africa a 17% chance of beating South Korea. Our swarm disagrees. Let me show you why."*

**0:15 — Question + Match (15s)**
Select "Who wins?" on the bracket. Hit Run SwarmCast.

**0:30 — Deliberation (30s)**
200 fish appear — 8 coloured schools, each labeled with its specialist and focus. *"Each school is an expert forming an independent opinion. They have never seen the Polymarket price."*

**1:00 — Critic fires (25s)**
*"The critic reads the full panel as one picture. It found a coverage gap — no agent assessed set-piece vulnerability. The orchestrator spawned a new agent."*

**1:25 — Delphi + LangGraph (20s)**
Schools begin aligning. *"LangGraph runs each specialist in its own thread for round 2. The contrarian held firm. One agent moved 4 points."*

**1:45 — Consensus (20s)**
*"SwarmCast says 37.7%. Polymarket says 16.7%. The spread is 21 points — above our 8-point threshold. SwarmCast places a limit order."*

**2:05 — Aggregate table (25s)**
*"Every agent, both rounds, their reasoning, the delta. The psychological analyst was the key signal — South Korea's big-game record is significantly stronger."*

**2:30 — Close (30s)**
*"No central coordinator told these agents what to conclude. The probability came from specialization, isolation, and iterative self-improvement. The fish are not decorative — they are the system. Check back in June."*

---

## 8. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| W&B Inference latency | Pre-cache one full run on demo match |
| Holistic critic too agreeable | System prompt forces gap-finding; floor: always spawn contrarian if absent |
| No Polymarket match market yet | Winner-odds H2H always produces a number (labeled "Polymarket (H2H)") |
| CLOB API wallet/auth fails | Edge detection is the key demo moment; bet placement is decoupled |
| WiFi unreliable | Mobile hotspot; backend local + ngrok |
| MCP subprocess too slow | 1h cache; pre-warm on server startup |

---

## The One-Liner

*SwarmCast: a self-improving multi-agent swarm built on CoreWeave that deliberates on World Cup matches, compares its prediction to Polymarket, bets when it disagrees, and gets smarter every time a match resolves.*
