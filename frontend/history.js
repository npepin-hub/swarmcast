/**
 * SwarmCast historical evaluation — /history page.
 * Connects to /history/ws, streams match evaluations, renders results table.
 */

let ws = null;
let totalMatches = 0;
let correctCount = 0;
let evaluatedCount = 0;
let confidenceSum = 0;
const rows = {};   // match_id → <tr>

function stageLabel(stage) {
  const map = {
    "group": "Group", "round of 16": "R16",
    "quarter_final": "QF", "semi_final": "SF", "final": "Final",
  };
  return map[stage.toLowerCase()] || stage;
}

function initRows(matches) {
  totalMatches = matches.length;
  const tbody = document.getElementById("eval-rows");
  tbody.innerHTML = "";
  document.getElementById("summary-bar").style.display = "flex";
  updateStats();

  for (const m of matches) {
    const tr = document.createElement("tr");
    tr.id = `row-${m.match_id}`;
    tr.innerHTML = `
      <td><span class="stage-badge">${stageLabel(m.stage)}${m.group ? " " + m.group : ""}</span></td>
      <td><strong>${m.team_a}</strong> <span style="color:var(--muted)">vs</span> <strong>${m.team_b}</strong></td>
      <td><span class="score-chip">${m.score}</span></td>
      <td>${m.actual_winner === "draw" ? "<em>Draw</em>" : m.actual_winner}</td>
      <td id="pred-${m.match_id}" class="result-pending">—</td>
      <td id="conf-${m.match_id}">—</td>
      <td id="verdict-${m.match_id}" class="result-pending running-pulse">…</td>
    `;
    tbody.appendChild(tr);
    rows[m.match_id] = tr;
  }
}

function updateStats() {
  const acc = evaluatedCount ? (correctCount / evaluatedCount) : null;
  document.getElementById("stat-accuracy").textContent = acc !== null ? `${(acc * 100).toFixed(0)}%` : "—";
  document.getElementById("stat-correct").textContent   = correctCount;
  document.getElementById("stat-total").textContent     = `${evaluatedCount} / ${totalMatches}`;
  const avgConf = evaluatedCount ? confidenceSum / evaluatedCount : null;
  document.getElementById("stat-avg-conf").textContent  = avgConf !== null ? `${(avgConf * 100).toFixed(0)}%` : "—";
}

function applyResult(data) {
  evaluatedCount++;
  if (data.correct) correctCount++;
  confidenceSum += data.confidence || 0;

  const predEl   = document.getElementById(`pred-${data.match_id}`);
  const confEl   = document.getElementById(`conf-${data.match_id}`);
  const verdictEl = document.getElementById(`verdict-${data.match_id}`);
  if (!predEl) return;

  const pct = ((data.probability ?? 0.5) * 100).toFixed(1);
  predEl.innerHTML = `${data.predicted} <small style="color:var(--muted)">(${pct}%)</small>`;
  predEl.classList.remove("result-pending");

  const conf = data.confidence ?? 0.5;
  const confPct = (conf * 100).toFixed(0);
  confEl.innerHTML = `
    <span class="conf-bar"><span class="conf-fill" style="width:${confPct}%"></span></span>
    ${confPct}%
  `;

  verdictEl.classList.remove("running-pulse", "result-pending");
  if (data.correct) {
    verdictEl.className = "result-correct";
    verdictEl.textContent = "✓";
  } else {
    verdictEl.className = "result-incorrect";
    verdictEl.textContent = "✗";
  }

  updateStats();
}

function markRunning(match_id) {
  const el = document.getElementById(`pred-${match_id}`);
  if (el) { el.className = "running-pulse"; el.textContent = "running…"; }
}

function markError(match_id, msg) {
  const el = document.getElementById(`verdict-${match_id}`);
  if (el) { el.className = "result-incorrect"; el.textContent = "err"; el.title = msg; }
  evaluatedCount++;
  updateStats();
}

function runEval() {
  if (ws) { ws.close(); ws = null; }

  correctCount = 0;
  evaluatedCount = 0;
  confidenceSum = 0;
  totalMatches = 0;

  const btn = document.getElementById("run-btn");
  btn.disabled = true;
  btn.textContent = "Running…";

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/history/ws`);

  ws.onmessage = (ev) => {
    const msg = JSON.parse(ev.data);
    switch (msg.type) {
      case "matches":
        initRows(msg.data);
        // Mark all rows as queued
        msg.data.forEach(m => markRunning(m.match_id));
        break;
      case "running":
        markRunning(msg.match_id);
        break;
      case "result":
        applyResult(msg);
        break;
      case "error":
        markError(msg.match_id, msg.message);
        break;
      case "complete":
        btn.disabled = false;
        btn.textContent = "Run Again";
        if (msg.weave_summary) {
          console.log("[weave] evaluation summary:", msg.weave_summary);
        }
        break;
    }
  };

  ws.onerror = () => { btn.disabled = false; btn.textContent = "Run Evaluation"; };
  ws.onclose = () => { if (btn.disabled) { btn.disabled = false; btn.textContent = "Run Evaluation"; } };
}
