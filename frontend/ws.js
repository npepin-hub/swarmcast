/**
 * WebSocket client + run button handler.
 * Drives Boids phase transitions, renders agent cards, critic, consensus.
 */

// ── Question templates ────────────────────────────────────────────────────────

const QUESTION_TEMPLATES = {
  who_wins:    (a, b) => `Who wins ${a} vs ${b} in a World Cup match? Provide a win probability for each team and a confidence score between 0.0 and 1.0.`,
  final_score: (a, b) => `Predict the final score for ${a} vs ${b} in a World Cup match. Provide goals for each team and a confidence score between 0.0 and 1.0.`,
  first_scorer:(a, b) => `Which team scores the first goal in ${a} vs ${b} in a World Cup match? Provide a probability and confidence score between 0.0 and 1.0.`,
  both_score:  (a, b) => `Will both ${a} and ${b} score in their World Cup match? Provide a probability and confidence score between 0.0 and 1.0.`,
  over_goals:  (a, b) => `Will there be more than 2.5 total goals in ${a} vs ${b} in a World Cup match? Provide a probability and confidence score between 0.0 and 1.0.`,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────

const show = id => document.getElementById(id)?.classList.remove("hidden");
const hide = id => document.getElementById(id)?.classList.add("hidden");
const setText = (id, text) => { const el = document.getElementById(id); if (el) el.textContent = text; };

let currentTeamA = "";
let currentTeamB = "";

// ── Role legend ───────────────────────────────────────────────────────────────

function renderLegend(specialists) {
  const legend = document.getElementById("role-legend");
  if (!legend) return;
  legend.innerHTML = specialists.map(s => {
    const hue = (window.ROLE_HUES?.[s.role] ?? 55);
    const color = `hsl(${hue}, 80%, 65%)`;
    return `<span class="legend-item">
      <span class="legend-dot" style="background:${color}"></span>
      ${s.role.replace(/_/g, " ")}
    </span>`;
  }).join("");
}

// ── Agent cards ───────────────────────────────────────────────────────────────

function agentColor(role) {
  const hue = window.ROLE_HUES?.[role] ?? 55;
  return `hsl(${hue}, 70%, 60%)`;
}

const barState = {};

function teamAName() {
  return window.selectedMatch?.team_a || "Team A";
}

const votesByRole = {};    // role → { r1: AgentVote, r2: AgentVote }
const focusByRole = {};    // role → focus string from specialist definition

function addAgentCard(vote) {
  if (!votesByRole[vote.role]) votesByRole[vote.role] = {};
  votesByRole[vote.role][`r${vote.round}`] = vote;

  const container = document.getElementById("agent-cards");
  const existing  = document.getElementById(`card-${vote.role}`);
  const card      = existing || document.createElement("div");
  const color     = agentColor(vote.role);
  const r1        = votesByRole[vote.role].r1;
  const r2        = votesByRole[vote.role].r2;

  card.id    = `card-${vote.role}`;
  card.className = "agent-card";
  card.style.borderLeftColor = color;

  const r1Row = r1 ? `
    <div class="round-row">
      <span class="round-tag">R1</span>
      <span class="round-pct">${(r1.probability * 100).toFixed(1)}%</span>
      <span class="prob-label">P(${teamAName()} wins)</span>
    </div>` : "";

  const r2Row = r2 ? `
    <div class="round-row round2-row">
      <span class="round-tag r2">R2</span>
      <span class="round-pct">${(r2.probability * 100).toFixed(1)}%</span>
      <span class="prob-label">P(${teamAName()} wins)</span>
      ${r1 ? `<span class="delta ${r2.probability >= r1.probability ? "up" : "dn"}">
        ${r2.probability >= r1.probability ? "+" : ""}${((r2.probability - r1.probability) * 100).toFixed(1)}pp
      </span>` : ""}
    </div>` : "";

  const latest = r2 || r1;
  card.innerHTML = `
    <div class="role" style="color:${color}">${vote.role.replace(/_/g, " ")}</div>
    ${r1Row}${r2Row}
    <div class="signal"><strong>Key signal:</strong> ${latest.key_signal}</div>
    <div class="reasoning">${latest.reasoning}</div>
    ${latest.uncertainty_flag ? '<div class="flag">⚠ Low data confidence</div>' : ""}
  `;

  if (!existing) container.appendChild(card);
  updateBarChart(vote, color);
  window.pulseRole?.(vote.role);
}

function updateBarChart(vote, color) {
  barState[vote.role] = { p: vote.probability, color };
  const bars = document.getElementById("bars");
  bars.innerHTML = Object.entries(barState)
    .sort(([, a], [, b]) => b.p - a.p)
    .map(([role, { p, color }]) => `
      <div class="bar-row">
        <div class="bar-role" style="color:${color}">${role.replace(/_/g, " ")}</div>
        <div class="bar-fill" style="width:${(p * 280).toFixed(0)}px; background:${color}"></div>
        <div class="bar-val">${(p * 100).toFixed(1)}%</div>
      </div>
    `).join("");
}

// ── Critic + consensus ────────────────────────────────────────────────────────

function renderCritique(critique) {
  show("critic-panel");
  document.getElementById("critic-gaps").innerHTML =
    "<strong>Coverage gaps</strong><ul>" +
    critique.coverage_gaps.map(g => `<li>${g}</li>`).join("") + "</ul>";
  document.getElementById("critic-groupthink").innerHTML =
    "<strong>Groupthink signals</strong><ul>" +
    critique.groupthink_signals.map(g => `<li>${g}</li>`).join("") + "</ul>";
  document.getElementById("critic-actions").innerHTML =
    "<strong>Actions</strong><ul>" +
    critique.recommended_actions.map(a =>
      `<li><code>${a.action}</code> — ${a.rationale}</li>`
    ).join("") + "</ul>";
}

function renderConsensus(consensus) {
  show("result-panel");
  const team    = teamAName();
  const pct     = (consensus.probability * 100).toFixed(1);
  const lo      = (consensus.ci_low  * 100).toFixed(1);
  const hi      = (consensus.ci_high * 100).toFixed(1);
  const scoreA  = Math.round(consensus.team_a_goals ?? 0);
  const scoreB  = Math.round(consensus.team_b_goals ?? 0);
  const nAgents = consensus.all_votes?.length ?? Object.keys(votesByRole).length;
  const dissent = consensus.minority_dissent?.length ?? 0;

  setText("consensus-score", `${scoreA}–${scoreB}`);
  setText("score-team-a", window.selectedMatch?.team_a || "");
  setText("score-team-b", window.selectedMatch?.team_b || "");
  setText("consensus-p", `${pct}%`);
  setText("consensus-team-label", `predicted score · P(${team} wins)`);
  setText("consensus-plain", "");   // verdict fills this when it arrives

  const dissentEl = document.getElementById("consensus-dissent");
  let ciText = `80% CI [${lo}%, ${hi}%]`;
  if (dissent > 0) ciText += ` · ${dissent} agent${dissent > 1 ? "s" : ""} dissented`;
  dissentEl.textContent = ciText;
  dissentEl.classList.remove("hidden");

  show("bar-chart");
  renderAggregateTable();
  hide("agent-feed");
}

function renderAggregateTable() {
  const wrap = document.getElementById("aggregate-table-wrap");
  const tbody = document.getElementById("aggregate-rows");
  if (!wrap || !tbody) return;

  const rows = Object.entries(votesByRole).map(([role, rounds]) => {
    const r1 = rounds.r1;
    const r2 = rounds.r2 || r1;
    const color = agentColor(role);
    const delta = r2 && r1 ? ((r2.probability - r1.probability) * 100).toFixed(1) : "—";
    const deltaStr = delta !== "—"
      ? (parseFloat(delta) >= 0 ? `+${delta}pp` : `${delta}pp`)
      : "—";
    const fmt = (v) => v
      ? `${v.team_a_goals}–${v.team_b_goals} · ${(v.probability * 100).toFixed(1)}%`
      : "—";
    const focus = focusByRole[role] || "";
    return `<tr>
      <td style="color:${color}">
        <div style="font-weight:600">${role.replace(/_/g, " ")}</div>
        ${focus ? `<div class="agg-focus">${focus}</div>` : ""}
      </td>
      <td>${fmt(r1)}</td>
      <td>${fmt(r2)}
        <span class="delta ${parseFloat(delta) >= 0 ? "up" : "dn"}">${deltaStr}</span>
      </td>
      <td class="agg-signal">${r2?.key_signal || r1?.key_signal || ""}</td>
      <td class="agg-reasoning">${r2?.reasoning || r1?.reasoning || ""}</td>
    </tr>`;
  });

  tbody.innerHTML = rows.join("");
  wrap.classList.remove("hidden");
}

function renderVerdict(text) {
  setText("consensus-plain", text);
}

function renderMatchMarkets(m) {
  show("match-markets-display");
  const vol = m.volume_24h ? `$${Number(m.volume_24h).toLocaleString("en",{maximumFractionDigits:0})} 24h vol` : "";
  const outcomes = [
    { label: m.team_a,  p: m.team_a_win,  color: "var(--accent)" },
    { label: "Draw",    p: m.draw,         color: "var(--muted)"  },
    { label: m.team_b,  p: m.team_b_win,  color: "var(--green)"  },
  ];
  const maxP = Math.max(...outcomes.map(o => o.p), 0.01);
  document.getElementById("match-markets-rows").innerHTML = `
    <div class="odds-note" style="margin-bottom:0.6rem">90-min result · ${vol}</div>
    ${outcomes.map(o => `
      <div class="odds-bar-row">
        <span class="odds-bar-label" style="width:110px">${o.label}</span>
        <div class="odds-bar-track">
          <div class="odds-bar-fill" style="width:${Math.max(4, Math.round((o.p/maxP)*220))}px;background:${o.color}"></div>
        </div>
        <span class="odds-bar-val" style="color:${o.color}">${(o.p*100).toFixed(1)}%</span>
      </div>`).join("")}
  `;
}

function oddsBar(p, maxP, color) {
  const w = Math.max(4, Math.round((p / maxP) * 220));
  return `<div class="odds-bar-fill" style="width:${w}px;background:${color}"></div>`;
}

function renderWinnerOdds({ teams, h2h, favorites }) {
  show("winner-odds-display");

  // H2H split bar — visual face-off
  let h2hHtml = "";
  if (h2h) {
    const [[teamA, pA], [teamB, pB]] = Object.entries(h2h).sort(([,a],[,b]) => b - a);
    h2hHtml = `
      <div class="odds-subsection">
        <div class="odds-label">Market-implied match odds</div>
        <div class="h2h-split">
          <span class="h2h-team">${teamA}</span>
          <div class="h2h-track">
            <div class="h2h-bar-a" style="width:${(pA*100).toFixed(1)}%"></div>
            <div class="h2h-bar-b" style="width:${(pB*100).toFixed(1)}%"></div>
          </div>
          <span class="h2h-team right">${teamB}</span>
        </div>
        <div class="h2h-pcts">
          <span>${(pA*100).toFixed(1)}%</span><span>${(pB*100).toFixed(1)}%</span>
        </div>
        <div class="odds-note">Derived by normalising tournament winner odds</div>
      </div>`;
  }

  // Tournament winner odds — horizontal bars
  const maxTeamP = Math.max(...Object.values(teams).map(s => s.market_probability), 0.01);
  const teamHtml = `
    <div class="odds-subsection">
      <div class="odds-label">Tournament winner odds</div>
      ${Object.entries(teams).map(([team, snap]) => {
        const p = snap.market_probability;
        const vol = snap.volume_24h ? `$${Number(snap.volume_24h).toLocaleString("en",{maximumFractionDigits:0})}` : "";
        return `<div class="odds-bar-row">
          <span class="odds-bar-label">${team}</span>
          <div class="odds-bar-track">${oddsBar(p, maxTeamP, "var(--accent)")}</div>
          <span class="odds-bar-val">${(p*100).toFixed(1)}%</span>
          <span class="odds-bar-vol">${vol}</span>
        </div>`;
      }).join("")}
    </div>`;

  // Top WC favorites — green bars
  const favHtml = favorites?.length ? (() => {
    const maxP = favorites[0].probability;
    return `<div class="odds-subsection">
      <div class="odds-label">WC2026 top favorites</div>
      ${favorites.map((f, i) => `
        <div class="odds-bar-row">
          <span class="odds-bar-label"><span class="fav-rank">${i+1}</span>${f.team}</span>
          <div class="odds-bar-track">${oddsBar(f.probability, maxP, "var(--green)")}</div>
          <span class="odds-bar-val">${(f.probability*100).toFixed(1)}%</span>
        </div>`).join("")}
    </div>`;
  })() : "";

  document.getElementById("winner-odds-rows").innerHTML = h2hHtml + teamHtml + favHtml;
}

function renderMarket(snapshot, spread) {
  const isDerived = snapshot.market_id === "winner_odds_derived";
  // Update Polymarket column sublabel
  const lbl = document.querySelector("#polymarket-col .prob-col-label, .prob-col:nth-child(3) .prob-col-label");
  if (lbl) lbl.textContent = isDerived ? "Polymarket (H2H)" : "Polymarket";

  const swarmPct  = parseFloat(document.getElementById("consensus-p")?.textContent) || 0;
  const mPct      = (snapshot.market_probability * 100).toFixed(1);
  const spreadPp  = (spread * 100).toFixed(1);
  const team      = teamAName();
  const threshold = 8.0;

  // Inline comparison
  setText("market-p-inline", `${mPct}%`);

  const badge   = document.getElementById("spread-badge");
  const verdict = document.getElementById("edge-verdict");
  const isEdge  = parseFloat(spreadPp) >= threshold;
  badge.textContent = `${spreadPp}pp`;
  badge.className   = `spread-badge ${isEdge ? "edge" : "no-edge"}`;
  badge.title = (
    `Edge = |SwarmCast (${swarmPct}%) − Polymarket (${mPct}%)| = ${spreadPp}pp.\n` +
    `Threshold: ${threshold}pp.\n` +
    (isEdge
      ? `Above threshold — SwarmCast places a limit order.`
      : `Below threshold — no bet placed.`)
  );
  verdict.textContent = isEdge ? "bet placed" : "no bet";
  show("spread-col");

  // Keep legacy market-display in sync (hidden but used elsewhere)
  setText("market-p", `${mPct}%`);
  setText("spread-label",
    `The crowd gives ${team} a ${mPct}% chance — ` +
    `${spreadPp} percentage points away from SwarmCast's estimate.`
  );
}

function renderEdge(edgeDetected, betReceipt) {
  show("edge-display");
  const badge = document.getElementById("edge-badge");
  if (badge) {
    badge.className = `edge-badge ${edgeDetected ? "edge" : "no-edge"}`;
    badge.textContent = edgeDetected ? "EDGE DETECTED — order placed" : "No edge — threshold not met";
  }
  if (betReceipt) {
    document.getElementById("bet-receipt").textContent = JSON.stringify(betReceipt, null, 2);
  }
}

// ── WebSocket event handler ───────────────────────────────────────────────────

function handleEvent(msg) {
  switch (msg.event) {
    case "spawning":
      window.assignRoles?.(msg.payload);
      renderLegend(msg.payload);
      msg.payload.forEach(s => { if (s.focus) focusByRole[s.role] = s.focus; });
      window.setSwarmPhase?.("deliberating");
      break;
    case "agent_vote":
      addAgentCard(msg.payload);
      window.updateBoidVote?.(msg.payload.role, msg.payload.probability);
      break;
    case "critic_fired":
      window.setSwarmPhase?.("critic");
      renderCritique(msg.payload);
      break;
    case "delphi_round":
      window.setSwarmPhase?.("delphi");
      addAgentCard(msg.payload);
      window.updateBoidVote?.(msg.payload.role, msg.payload.probability);
      break;
    case "consensus":
      window.setSwarmPhase?.("consensus");
      window.lockConsensusColor?.(msg.payload.probability);
      renderConsensus(msg.payload);
      break;
    case "verdict":
      renderVerdict(msg.payload.text);
      break;
    case "match_markets":
      renderMatchMarkets(msg.payload);
      break;
    case "winner_odds":
      renderWinnerOdds(msg.payload);
      break;
    case "market_check":
      if (msg.payload.snapshot) renderMarket(msg.payload.snapshot, msg.payload.spread);
      break;
    case "winner_odds":
      // Fallback: populate Polymarket column from tournament H2H if no match market
      if (!document.getElementById("market-p-inline")?.textContent.match(/\d/)) {
        const h2h = msg.payload.h2h;
        const team = teamAName();
        const p = h2h?.[team];
        if (p != null) {
          const pct = (p * 100).toFixed(1);
          const swarmPct = parseFloat(document.getElementById("consensus-p")?.textContent) || 0;
          const spread = Math.abs(swarmPct / 100 - p);
          renderMarket({ market_probability: p, market_id: "winner_odds_derived" }, spread);
        }
      }
      break;
    case "edge_result":
      renderEdge(msg.payload.edge_detected, msg.payload.bet_receipt);
      break;
    case "error":
      console.error("[swarmcast]", msg.payload);
      break;
  }
}

// ── Question card selection ───────────────────────────────────────────────────

let selectedQuestion = "who_wins";

const QUESTION_LABELS = {
  who_wins:     "Who wins?",
  final_score:  "Predict the final score",
  first_scorer: "Who scores first?",
  both_score:   "Both teams to score?",
  over_goals:   "Over 2.5 goals?",
};

document.querySelectorAll(".q-card").forEach(card => {
  card.addEventListener("click", () => {
    document.querySelectorAll(".q-card").forEach(c => c.classList.remove("active"));
    card.classList.add("active");
    selectedQuestion = card.dataset.q;
    updateRunBar();
  });
});

function updateRunBar() {
  const match = window.selectedMatch;
  if (!match) return;
  const qlabel = document.getElementById("run-bar-question-label");
  if (qlabel) qlabel.textContent = QUESTION_LABELS[selectedQuestion] || selectedQuestion;
  const matchLabel = document.getElementById("selected-match-label");
  if (matchLabel) {
    const datePart = match.match_date
      ? new Date(match.match_date + "T00:00:00Z").toLocaleDateString("en-US", {
          month: "short", day: "numeric", year: "numeric", timeZone: "UTC",
        })
      : "";
    const meta = [match.competition, datePart].filter(Boolean).join(" · ");
    matchLabel.textContent = meta ? `${match.label} · ${meta}` : match.label;
  }
  document.getElementById("run-bar").classList.remove("hidden");
}

// Expose so bracket.js can call it when a match is selected
window.onMatchSelected = updateRunBar;

// ── Run button ────────────────────────────────────────────────────────────────

document.getElementById("run-btn").addEventListener("click", async () => {
  const match = window.selectedMatch;
  if (!match) return;

  const tmpl = QUESTION_TEMPLATES[selectedQuestion] ?? QUESTION_TEMPLATES.who_wins;
  const matchQuery = tmpl(match.team_a, match.team_b);

  // Reset output
  document.getElementById("agent-cards").innerHTML = "";
  document.getElementById("bars").innerHTML = "";
  document.getElementById("role-legend").innerHTML = "";
  Object.keys(barState).forEach(k => delete barState[k]);
  ["critic-panel", "result-panel", "match-markets-display", "winner-odds-display",
   "market-display", "edge-display"].forEach(hide);
  Object.keys(votesByRole).forEach(k => delete votesByRole[k]);
  Object.keys(focusByRole).forEach(k => delete focusByRole[k]);
  const aggWrap = document.getElementById("aggregate-table-wrap");
  if (aggWrap) aggWrap.classList.add("hidden");
  show("viz-panel");
  show("agent-feed");
  window.resetBoids?.();
  window.setSwarmPhase?.("deliberating");
  currentTeamA = match.team_a;
  currentTeamB = match.team_b;
  document.getElementById("viz-panel").scrollIntoView({ behavior: "smooth", block: "start" });

  const body = {
    match_query: matchQuery,
    team_a: match.team_a,
    team_b: match.team_b,
    home_team_code: match.home_team_code || "",
    away_team_code: match.away_team_code || "",
    match_date: match.match_date || "",
    competition: match.competition || "",
    competition_id: match.competition_id || match.group || "",
    match_id: match.match_id || "",
    polymarket_market_id: document.getElementById("market-id").value.trim(),
  };

  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  btn.textContent = "Running…";
  try {
    const res = await fetch("/forecast", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) console.error("Forecast error", await res.text());
  } finally {
    btn.disabled = false;
    btn.textContent = "Run SwarmCast";
  }
});

// ── WebSocket connection ──────────────────────────────────────────────────────

let socket = null;

function connect() {
  socket = new WebSocket(`ws://${location.host}/ws`);
  socket.onmessage = (ev) => { try { handleEvent(JSON.parse(ev.data)); } catch {} };
  socket.onclose   = () => setTimeout(connect, 2000);
}

connect();
