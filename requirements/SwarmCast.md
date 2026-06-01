# SwarmCast
### A Self-Improving Multi-Agent Swarm for World Cup Match Forecasting
*with Polymarket Edge Detection and Automated Bet Placement*

> "Feed it a World Cup match. A swarm of specialist agents deliberates in isolation, a self-improving critic rewrites the swarm in real time, and emergent consensus appears — visualized as a school of fish finding direction."

*Multi-Agent Orchestration Hackathon · MIT / The Engine, Cambridge MA · May 31, 2026 · #BosTechWeek*

---

## 1. The Core Idea

SwarmCast is a multi-agent deliberation system for World Cup 2026 match forecasting. A meta-orchestrator reads a match question and dynamically spawns a pool of N specialist agents — each with a narrow analytical lens, a named focus area, and live access to MCP data. Agents deliberate in parallel in full isolation, forming independent opinions before any aggregation. A holistic critic reads the full panel and identifies what the collective intelligence is missing — coverage gaps, groupthink signals, blind spots specific to this match — then the orchestrator acts (spawn / rewrite / broadcast). The swarm then runs **N configurable revision rounds** (default: 5), each building on the last, with every agent tracking its vote trajectory across all rounds. A confidence-weighted consensus probability, predicted score, and 80% confidence interval emerge — shaped in part by the contrarian agent, which is always guaranteed to be in the pool.

The consensus is compared side-by-side to Polymarket — either a live match market when available, or a head-to-head probability derived from live tournament winner markets. If the spread exceeds 8 percentage points, SwarmCast places a limit order. Every inference call is traced in W&B Weave. A built-in backtest loop runs SwarmCast against 2022 World Cup matches — comparing predictions to known outcomes and building the labeled dataset for v2 fine-tuning on CoreWeave.

### Key Features

- **N-agent, N-round deliberation** — the number of specialist agents and revision rounds are both configurable (`deliberation_rounds = 5` default). Not a fixed 2-round pipeline — a genuine iterative swarm.
- **Guaranteed contrarian** — `ensure_contrarian()` is called after spawning and after every critic action. The pool always contains a structurally biased dissenter.
- **Multi-round vote tracking** — every agent's vote is tracked across all rounds. The UI shows the full trajectory: R1 → R2 → ... → RN, with flip detection and confidence delta per agent.
- **MCP tools baked into agents** — specialists call `wc26-mcp` and `@zafronix/wc-mcp` directly as LangChain tools. Disk-cached for resilience across server restarts.
- **Self-improving critic loop** — after round 1, the holistic critic reads the full panel, identifies gaps and groupthink, and the orchestrator spawns new agents, rewrites weak prompts, or broadcasts gap signals before the revision rounds.
- **2022 WC backtest** — `backend/eval/` runs SwarmCast against completed 2022 matches with known outcomes. Results persisted to disk, accessible at `/history`. This is the closed-loop evaluation that produces the training signal.
- **Falsifiable claim** — predicted score, win probability, confidence interval, minority dissent report, and explicit spread against Polymarket. Verifiable against 2022 history now, 2026 results in June.
- **Polymarket always visible** — pre-tournament, live winner market odds ($517M volume) are converted to head-to-head probability so the comparison is never empty.

### Specialist Agents

`tactical_analyst` · `historical_stats` · `current_form` · `squad_fitness` · `tournament_context` · `set_piece_specialist` · `psychological_analyst` · `contrarian`

### Adversarial Design — The Contrarian and the Critic

SwarmCast has two built-in mechanisms against consensus bias. Together they function as the system's immune system.

**The Contrarian** is the only agent with a guaranteed structural role in every swarm. `ensure_contrarian()` is called twice — once after the orchestrator spawns the initial pool, and again after every critic action. It cannot be pruned, cannot be skipped, and holds the widest tool access of any specialist (all profile, form, and history tools) precisely so it has no excuse for missing the underdog case. Its job is to surface the single most credible mechanism for an upset, and it is structurally biased against the favourite to do so. In practice, it is the primary source of minority dissent and the main reason the confidence interval doesn't collapse to a point estimate.

**The Holistic Critic** does not challenge individual agents. It reads the full panel as one unified document and asks a different question: *what is this collective blind to about this specific match?* It returns three outputs — coverage gaps (topics no agent analyzed), groupthink signals (agents converging without independent evidence), and recommended actions. The orchestrator then acts structurally: spawning new agents for identified gaps, rewriting prompts for agents exhibiting groupthink, or broadcasting gap signals to the full pool before the next revision round. This is what makes the system self-improving rather than a static ensemble.

**How the system adapts:** after the critic fires, the swarm is not the same swarm that ran round 1. Prompts have been rewritten. New agents may have joined. The gap signal has been injected. Revision rounds 2..N run on this evolved pool — which is why later rounds often show meaningful probability shifts from agents that updated based on the new context, not just anchoring.

### Edge Detection — A Note on Bet Placement

SwarmCast computes the spread between its consensus probability and the Polymarket implied price. When the spread exceeds the configured threshold, it displays an edge badge and flags the opportunity. **Actual order placement via the CLOB API is not wired through in this demo.** The `place_limit_order()` function exists in the codebase but raises `NotImplementedError` by design.

This is intentional. The ability for agentic systems to autonomously execute financial transactions — including trades on prediction markets — sits in a legally ambiguous and rapidly evolving space. Depending on jurisdiction, such activity may be subject to securities regulation, gambling law, or financial services licensing requirements. Some US states explicitly restrict or prohibit participation in prediction markets for their residents, and federal treatment of blockchain-based prediction markets remains unsettled. The edge detection and spread calculation are the meaningful demonstration — the mechanics of a limit order are straightforward to wire once the legal context is established.

### Visualization

p5.js Boids — 25 fish per specialist school (200 fish total for 8 agents). Each school is color-coded with a centroid speech bubble showing role name and focus area. Per-fish randomisation (speed, turn rate, hue drift, size, wander offset) keeps schools lively. Phase transitions driven by WebSocket events mirror the deliberation state: idle → deliberating (chaos) → critic (turbulence) → delphi (partial alignment) → consensus (lock).

### Output

Predicted score · SwarmCast probability **VS** Polymarket implied probability · Edge badge (pp spread + hover tooltip explaining the calculation) · Aggregate agent table with round 1 → round 2 deltas, key signals, and full reasoning per agent.

---

## 2. System Architecture

### 2.1 Pipeline

```
match_query + team_a + team_b
        │
        ▼
[MCP Context]  wc26-mcp + @zafronix/wc-mcp — 13 parallel calls via asyncio.gather
               Results disk-cached for resilience across restarts
        │
        ▼
[Meta-Orchestrator]  Qwen3-14B via W&B Inference
  → writes N specialist definitions (role, focus, system_prompt, data_slice_id)
  → ensure_contrarian() guarantees dissenter is always present
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
  → ensure_contrarian() called again after critic actions
        │
        ▼
[Revision Rounds 2..N]  configurable (default N=5)
  → each round: run_revision_round() — agents see aggregate P only
  → all round votes tracked: round_votes: list[list[AgentVote]]
  → flip detection + confidence delta computed per agent per round
        │
        ▼
[Consensus]  confidence-weighted P + 80% CI + minority dissent
             score consensus from all final votes
        │
        ▼
[Polymarket Validation]  first and only contact with Polymarket
  → match market if available; falls back to winner-odds H2H
  → edge = |SwarmCast P − market P|; if > 8pp → CLOB limit order
        │
        ▼
[Output]  consensus tile + VS Polymarket + full round history table
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

## 3. The Loops

SwarmCast has three distinct feedback loops operating at different timescales. Together they are what make the system self-improving rather than a one-shot pipeline.

### Loop 1 — Deliberation (seconds)

The core round-trip: specialist agents form independent opinions → critic reads the full panel → orchestrator acts → Delphi round 2. This loop runs once per forecast and produces the consensus. It is visible in real time as the fish schools go from chaotic to aligned.

```
Round 1 votes
    → Critic (coverage gaps + groupthink)
    → Orchestrator (spawn / rewrite / broadcast)
    → Round 2 votes (LangGraph Swarm)
    → Consensus
```

### Loop 2 — Backtest Evaluation (runs now against 2022 data)

`backend/eval/` runs SwarmCast against completed 2022 World Cup matches with known outcomes. The backtest samples matches from `@zafronix/wc-mcp`, runs the full deliberation pipeline, and compares the consensus to the actual result. Results are persisted to disk (`wc2022_match_cache.json`) and accessible at `/history` in the UI.

This is not a future feature — it runs today. Every backtest run produces labeled traces in W&B Weave.

```
2022 WC matches (known outcomes)
    → run_deliberation() for each match
    → judge_prediction(consensus, actual_winner)
    → Labeled Weave trace (correct / incorrect / edge)
    → /history page shows swarm accuracy across matches
```

### Loop 3 — Market Feedback (hours, post-June 11)

After a 2026 match resolves, the ground truth is labeled on the live forecast trace. Combined with backtest traces, this builds the training dataset.

```
Live forecast + bet
    → Match resolves June 11+
    → label_trace(call_id, outcome)
    → Merged with backtest traces → full labeled dataset
```

### Loop 4 — Model Improvement (CoreWeave fine-tuning)

With labeled traces from both backtest and live forecasts, specialist models are fine-tuned on CoreWeave. Agents that consistently underperformed — high round-to-round deltas, high uncertainty flags, wrong direction vs ground truth — are prioritized for retraining.

```
Labeled Weave traces (backtest + live)
    → Identify underperforming specialist patterns
    → Fine-tune on CoreWeave GPUs
    → Redeploy smarter specialists for next match
```

---

## 4. W&B Weave — Observability Layer

Weave is not an afterthought. It is instrumented from the first line of the pipeline and is the mechanism that makes all three loops computable.

### What is traced

Every function decorated with `@weave.op()` is captured as a Weave call with full input/output, latency, and model metadata:

| Function | What Weave captures |
|---|---|
| `spawn_specialists` | Match question → specialist definitions (role, focus, prompts) |
| `run_specialist` | System prompt + MCP context → vote (score, probability, reasoning) |
| `run_critic` | Full panel → coverage gaps, groupthink signals, recommended actions |
| `run_delphi_round` | R1 aggregate + specialist prompts → R2 votes per agent |
| `aggregate` | All votes → consensus P, CI, minority dissent |
| `run_market_validation` | Consensus P → Polymarket snapshot, spread, edge decision, bet receipt |
| `run_forecast_pipeline` | Full pipeline trace, end-to-end |

### What Weave enables

**Real-time debugging** — during the hackathon, every agent call is inspectable in the Weave dashboard at `wandb.ai/ceatp-ceatp/swarmcast/weave`. If an agent returns garbage, you see the exact prompt, the exact output, and the parse result.

**Agent comparison** — which specialist moved the most between R1 and R2? Which was the minority dissenter? Weave makes these comparisons immediate.

**Ground truth labeling** — after a match resolves, `label_trace(call_id, outcome)` attaches the result to the pipeline trace. This is the bridge from observability to training data.

**Dataset for v2** — every labeled pipeline trace is a (question, agent_outputs, consensus, outcome) training example. The dataset builds automatically as matches resolve through June and July.

### Weave dashboard URL

```
https://wandb.ai/ceatp-ceatp/swarmcast/weave
```

---

## 5. Data Sources

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
