/**
 * WebSocket client — connects to /ws, drives Boids phase transitions
 * and updates the DOM as agent events arrive.
 */

const WS_URL = `ws://${location.host}/ws`;
let socket = null;

// ── DOM helpers ───────────────────────────────────────────────────────────────

function show(id)   { document.getElementById(id)?.classList.remove("hidden"); }
function hide(id)   { document.getElementById(id)?.classList.add("hidden"); }
function setText(id, text) { const el = document.getElementById(id); if (el) el.textContent = text; }

function addAgentCard(vote) {
  const container = document.getElementById("agent-cards");
  const existing = document.getElementById(`card-${vote.role}`);
  const card = existing || document.createElement("div");
  card.id = `card-${vote.role}`;
  card.className = `agent-card${vote.round === 2 ? " round2" : ""}`;
  card.innerHTML = `
    <div class="role">${vote.role.replace(/_/g, " ")} · round ${vote.round}</div>
    <div class="prob">${(vote.probability * 100).toFixed(1)}%</div>
    <div class="signal">${vote.key_signal}</div>
    <div class="reasoning">${vote.reasoning}</div>
    ${vote.uncertainty_flag ? '<div class="flag">⚠ Low data confidence</div>' : ""}
  `;
  if (!existing) container.appendChild(card);
  updateBarChart(vote);
}

// Fallback bar chart
const barState = {};
function updateBarChart(vote) {
  barState[vote.role] = vote.probability;
  const bars = document.getElementById("bars");
  bars.innerHTML = Object.entries(barState)
    .sort(([, a], [, b]) => b - a)
    .map(([role, p]) => `
      <div class="bar-row">
        <div class="bar-role">${role.replace(/_/g, " ")}</div>
        <div class="bar-fill" style="width:${(p * 280).toFixed(0)}px"></div>
        <div class="bar-val">${(p * 100).toFixed(1)}%</div>
      </div>
    `).join("");
}

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
  badge.textContent = edgeDetected
    ? "EDGE DETECTED — order placed"
    : "No edge — threshold not met";
  if (betReceipt) {
    document.getElementById("bet-receipt").textContent =
      JSON.stringify(betReceipt, null, 2);
  }
}

// ── WebSocket event handler ───────────────────────────────────────────────────

function handleEvent(msg) {
  switch (msg.event) {
    case "spawning":
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

// ── Run button → POST /forecast ──────────────────────────────────────────────

document.getElementById("run-btn").addEventListener("click", async () => {
  const match = window.selectedMatch;
  if (!match) return;

  // Reset output panels
  document.getElementById("agent-cards").innerHTML = "";
  document.getElementById("bars").innerHTML = "";
  Object.keys(barState).forEach(k => delete barState[k]);
  ["critic-panel", "result-panel", "market-display", "edge-display"].forEach(hide);
  document.getElementById("viz-panel").classList.remove("hidden");
  document.getElementById("agent-feed").classList.remove("hidden");
  window.setSwarmPhase?.("deliberating");

  const body = {
    match_query: `Predict the final score for ${match.team_a} vs ${match.team_b} in a World Cup match. Provide goals for each team and a confidence score between 0.0 and 1.0.`,
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

// ── Connect WebSocket ─────────────────────────────────────────────────────────

function connect() {
  socket = new WebSocket(WS_URL);
  socket.onmessage = (ev) => {
    try { handleEvent(JSON.parse(ev.data)); } catch {}
  };
  socket.onclose = () => setTimeout(connect, 2000);
}

connect();
