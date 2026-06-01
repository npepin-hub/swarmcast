# SwarmCast — Video Script & GitHub GIF Guide
*Mexico vs South Africa · Group A · June 11 2026*

---

## HOW TO ADD ON-SCREEN TEXT OVERLAYS

Use **Loom's built-in text tool** (click the text icon in the Loom toolbar while recording) or add them in post with **iMovie / CapCut / Descript**:
- Position: **bottom center**, ~80px from the bottom edge
- Font: clean sans-serif, white text, semi-transparent dark background pill
- Keep each card to **one short line** — it should be readable in 2 seconds
- Fade in: 0.2s · Hold: duration of the beat · Fade out: 0.2s

Each beat in the script below includes a `[TEXT OVERLAY]` line — the exact text to show on screen.

---

## PART 1 — GITHUB GIF (20–25 seconds, no audio)

A GIF lives in the README. No narration — the overlays carry the story.

### Setup before recording
- Window size: **1280 × 800**
- SwarmCast at `http://localhost:8000` — fully loaded, bracket visible
- "Who wins?" already active
- Group A tile in view — Mexico vs South Africa row visible
- Use **Kap**, **GIPHY Capture**, or `screencapture -d`
- Run the pipeline once before to warm the cache

### Shot sequence

| # | Action | Duration | On-screen overlay | What viewer sees |
|---|---|---|---|---|
| 1 | Hold on homepage | 1.5s | `SwarmCast — AI swarm forecasting` | Question cards + bracket |
| 2 | Click Mexico vs South Africa | 0.5s | `Pick a match` | Row highlights. Run bar appears. |
| 3 | Click Run SwarmCast | 0.5s | `The swarm composes itself` | Button press. Scroll to fish. |
| 4 | Fish appear — full chaos | 4s | `N specialist agents deliberating in isolation` | Colored schools, speech bubbles, labels |
| 5 | Critic phase | 2s | `Holistic critic fires — swarm evolves` | Brief turbulence, schools fragment |
| 6 | Delphi — schools align | 3s | `Delphi round — revision in progress` | Schools converging |
| 7 | Consensus locks | 2s | `Consensus reached` | Fish tight formation. Tile appears. |
| 8 | SwarmCast VS Polymarket | 3s | `Our prediction vs the market` | Score + % + edge badge |
| 9 | Agent table | 2s | `Every agent · every round · full reasoning` | Table rows |
| 10 | End frame | 1s | `SwarmCast · MIT/The Engine · June 2026` | Static hold |

**Total: ~20 seconds.** Loop-friendly.

### GIF tips
- Record at **2× speed** then slow to **0.8×** — fish look more dramatic
- Export at **800px wide**, ≤ 5MB for GitHub README inline display
- `ffmpeg -i capture.gif -vf "fps=15,scale=800:-1" out.gif`

---

## PART 2 — LOOM VIDEO (~90 seconds, with narration + overlays)

### Setup before recording
- SwarmCast at `http://localhost:8000`
- Polymarket tab ready: `https://polymarket.com/sports/world-cup/fifwc-mex-rsa-2026-06-11`
- "Who wins?" question card active
- Group A tile visible, Mexico vs South Africa row ready
- Microphone on. No other tabs visible.
- Run the pipeline once beforehand — use cached result for a clean live run.

---

### [0:00 — OPEN ON SWARMCAST]
*Shot: SwarmCast homepage. Question cards at top. Bracket below.*
`[TEXT OVERLAY]` **SwarmCast — a self-improving multi-agent swarm**

> "This is SwarmCast — a self-improving multi-agent swarm that forecasts World Cup matches and compares its prediction directly to Polymarket."

> "Let me show you how it works."

---

### [0:10 — PICK THE QUESTION]
*Action: gesture toward question cards*
`[TEXT OVERLAY]` **Step 1 — Choose your question**

> "First — you choose what you want to know. Who wins? Final score? Both teams to score?"

*Action: click "Who wins?"*
`[TEXT OVERLAY]` **Who wins? · Simple question · Hard problem**

> "Who wins. Simple question. Hard problem."

---

### [0:18 — PICK THE MATCH]
*Action: point to Group A tile. Hover over Mexico vs South Africa.*
`[TEXT OVERLAY]` **Step 2 — Pick the match**

> "Then you pick the match. Mexico versus South Africa — opening game of the 2026 World Cup."

*Action: click the row. Run bar slides in.*
`[TEXT OVERLAY]` **🇲🇽 Mexico vs 🇿🇦 South Africa · June 11**

*Action: click Run SwarmCast*
`[TEXT OVERLAY]` **Swarm is running...**

---

### [0:27 — THE SWARM SPAWNS]
*Shot: fish visualization. Schools explode onto screen.*
`[TEXT OVERLAY]` **Meta-orchestrator spawning specialist agents**

> "The meta-orchestrator reads the question and decides which experts it needs — on the fly, from the question alone."

*Shot: speech bubbles — 'xG · formations', 'WC history · H2H', 'underdog case · upset risk'*
`[TEXT OVERLAY]` **Each school = one specialist · each fish = one vote**

> "Each school is a specialist agent. Tacticians. Historians. Fitness analysts. Set piece specialists. A psychological profiler. And always — a contrarian, structurally arguing the other side."

`[TEXT OVERLAY]` **Agents have never seen the Polymarket price**

> "They have never seen the Polymarket price."

---

### [0:48 — CRITIC FIRES]
*Shot: critic panel appears below fish. Schools briefly scatter.*
`[TEXT OVERLAY]` **Holistic critic reading the full panel**

> "After round one, a holistic critic reads the full panel — not to challenge individual agents, but to find what the whole school is blind to."

`[TEXT OVERLAY]` **Coverage gap found · Orchestrator acts · Swarm evolves**

> "It spots a gap. The orchestrator acts — the swarm is not the same swarm it was."

---

### [0:58 — DELPHI + CONSENSUS]
*Shot: fish schools begin aligning.*
`[TEXT OVERLAY]` **Delphi round — specialists revise in isolation**

> "A Delphi round runs — each specialist revises, seeing only the aggregate probability. Not each other's reasoning."

*Shot: schools lock. Consensus tile slides in.*
`[TEXT OVERLAY]` **Consensus locked**

> "The consensus. A predicted score. A win probability."

*Shot: SwarmCast % VS Polymarket % visible.*
`[TEXT OVERLAY]` **Our prediction vs Polymarket — first time the market is revealed**

> "Compared directly to Polymarket — a market SwarmCast never looked at until this moment."

*Shot: edge badge.*
`[TEXT OVERLAY]` **Edge detected · threshold exceeded**

> "The spread exceeds our threshold. SwarmCast flags the edge."

---

### [1:14 — AGENT TABLE]
*Shot: scroll to aggregate table.*
`[TEXT OVERLAY]` **Every agent · every round · key signal · full reasoning**

> "Every agent's work is visible — both rounds, their key signal, their full reasoning, and how much they moved between rounds."

---

### [1:22 — CUT TO POLYMARKET]
*Action: switch to Polymarket tab.*
`[TEXT OVERLAY]` **The market SwarmCast was compared against**

> "This is the number we went up against. Live on Polymarket. Mexico vs South Africa. June 11th."

*Hold on the price for 3 seconds.*
`[TEXT OVERLAY]` **SwarmCast built its probability before seeing this**

> "SwarmCast built its probability before ever seeing this. That's what makes the edge real."

---

### [1:35 — CLOSE]
*Stay on Polymarket page.*
`[TEXT OVERLAY]` **No central coordinator · no hardcoded answers**

> "No central coordinator. No hardcoded answers. The swarm composes itself from the question."

`[TEXT OVERLAY]` **Check back June 11th**

> "Check back June 11th."

---

### [1:40 — END]
`[TEXT OVERLAY]` **SwarmCast · Built at MIT / The Engine · May 31 2026**

---

*Loom: ~90 seconds · GIF: ~20 seconds*
*Match: Mexico vs South Africa · Group A · June 11 2026*
*Polymarket: https://polymarket.com/sports/world-cup/fifwc-mex-rsa-2026-06-11*
