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

function addAgentCard(vote) {
  const container = document.getElementById("agent-cards");
  const existing  = document.getElementById(`card-${vote.role}`);
  const card      = existing || document.createElement("div");
  const color     = agentColor(vote.role);
  card.id         = `card-${vote.role}`;
  card.className  = `agent-card${vote.round === 2 ? " round2" : ""}`;
  card.style.borderLeftColor = color;
  card.innerHTML  = `
    <div class="role" style="color:${color}">${vote.role.replace(/_/g, " ")} · round ${vote.round}</div>
    <div class="prob">${(vote.probability * 100).toFixed(1)}%</div>
    <div class="signal">${vote.key_signal}</div>
    <div class="reasoning">${vote.reasoning}</div>
    ${vote.uncertainty_flag ? '<div class="flag">⚠ Low data confidence</div>' : ""}
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
  setText("consensus-p", `${(consensus.probability * 100).toFixed(1)}%`);
  setText("consensus-ci",
    `80% CI [${(consensus.ci_low * 100).toFixed(1)}%, ${(consensus.ci_high * 100).toFixed(1)}%]`
  );
}

function renderMarket(snapshot, spread) {
  show("market-display");
  setText("market-p", `${(snapshot.market_probability * 100).toFixed(1)}%`);
  setText("spread-label", `Spread: ${(spread * 100).toFixed(1)} pp`);
}

function renderEdge(edgeDetected, betReceipt) {
  show("edge-display");
  const badge = document.getElementById("edge-badge");
  badge.className = `edge-badge ${edgeDetected ? "edge" : "no-edge"}`;
  badge.textContent = edgeDetected ? "EDGE DETECTED — order placed" : "No edge — threshold not met";
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
      window.setSwarmPhase?.("deliberating");
      break;
    case "agent_vote":
      addAgentCard(msg.payload);
      break;
    case "critic_fired":
      window.setSwarmPhase?.("critic");
      renderCritique(msg.payload);
      break;
    case "delphi_round":
      window.setSwarmPhase?.("delphi");
      addAgentCard(msg.payload);
      break;
    case "consensus":
      window.setSwarmPhase?.("consensus");
      renderConsensus(msg.payload);
      break;
    case "market_check":
      if (msg.payload.snapshot) renderMarket(msg.payload.snapshot, msg.payload.spread);
      break;
    case "edge_result":
      renderEdge(msg.payload.edge_detected, msg.payload.bet_receipt);
      break;
    case "error":
      console.error("[swarmcast]", msg.payload);
      break;
  }
}

// ── Run button ────────────────────────────────────────────────────────────────

document.getElementById("run-btn").addEventListener("click", async () => {
  const match = window.selectedMatch;
  if (!match) return;

  const questionKey = document.getElementById("question-select").value;
  const tmpl = QUESTION_TEMPLATES[questionKey] ?? QUESTION_TEMPLATES.final_score;
  const matchQuery = tmpl(match.team_a, match.team_b);

  // Reset output
  document.getElementById("agent-cards").innerHTML = "";
  document.getElementById("bars").innerHTML = "";
  document.getElementById("role-legend").innerHTML = "";
  Object.keys(barState).forEach(k => delete barState[k]);
  ["critic-panel", "result-panel", "market-display", "edge-display"].forEach(hide);
  show("viz-panel");
  show("agent-feed");
  window.setSwarmPhase?.("deliberating");

  const body = {
    match_query: matchQuery,
    team_a: match.team_a,
    team_b: match.team_b,
    competition_id: match.group || "",
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
