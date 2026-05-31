/**
 * Tournament bracket — Group stage tiles + empty knockout stages.
 * Fetches /matches on load, renders everything, exposes window.selectedMatch.
 */

const KNOCKOUT_ROUNDS = [
  { label: "Round of 32", slots: 16 },
  { label: "Round of 16", slots: 8  },
  { label: "Quarter-finals", slots: 4 },
  { label: "Semi-finals",    slots: 2 },
  { label: "Final",          slots: 1 },
];

let selectedMatch = null;   // populated in selectMatch()

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00Z");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function selectMatch(row, match, groupId) {
  // Deselect previous
  document.querySelectorAll(".match-row.selected").forEach(r => r.classList.remove("selected"));
  row.classList.add("selected");

  const homeRaw = match.home_team_name || match.home_team_id || "TBD";
  const awayRaw = match.away_team_name || match.away_team_id || "TBD";

  // Strip leading flag emoji+space (flags = Regional Indicator pairs U+1F1E0-1F1FF)
  const stripFlag = s => s.replace(/^[\u{1F1E0}-\u{1F1FF}\p{Emoji_Presentation}\p{Extended_Pictographic}]+\s*/u, "").trim();
  const teamA = stripFlag(homeRaw);
  const teamB = stripFlag(awayRaw);

  const round = match.round || "Group Stage";
  const competition = groupId
    ? `${round} · Group ${groupId}`
    : round;

  selectedMatch = {
    team_a: teamA,
    team_b: teamB,
    home_team_code: (match.home_team_id || "").toLowerCase(),
    away_team_code: (match.away_team_id || "").toLowerCase(),
    match_date: match.date || "",
    competition_id: groupId || "",
    competition,
    round,
    group: groupId,
    match_id: match.id || "",
    label: `${homeRaw} vs ${awayRaw}`,
  };
  window.selectedMatch = selectedMatch;

  window.onMatchSelected?.();
}

// ── Group tiles ───────────────────────────────────────────────────────────────

function renderGroupTile(group) {
  const tile = document.createElement("div");
  tile.className = "group-tile";

  const header = document.createElement("div");
  header.className = "group-header collapsible";
  header.innerHTML = `Group ${group.id}<span class="group-chevron">▸</span>`;
  tile.appendChild(header);

  const teams = document.createElement("div");
  teams.className = "group-teams";
  (group.teams || []).forEach(t => {
    const span = document.createElement("span");
    span.className = "team-chip";
    span.textContent = `${t.flag_emoji || "🏳️"} ${t.name}`;
    teams.appendChild(span);
  });
  tile.appendChild(teams);

  const matchList = document.createElement("div");
  matchList.className = "match-list hidden";
  (group.matches || []).forEach(m => {
    const row = document.createElement("div");
    row.className = "match-row";
    const home = m.home_team_name || m.home_team_id || "TBD";
    const away = m.away_team_name || m.away_team_id || "TBD";
    row.innerHTML = `
      <span class="match-teams">${home} <span class="vs-dot">·</span> ${away}</span>
      <span class="match-date">${fmtDate(m.date)}</span>
    `;
    row.addEventListener("click", () => selectMatch(row, m, group.id));
    matchList.appendChild(row);
  });
  tile.appendChild(matchList);

  header.addEventListener("click", () => {
    const open = matchList.classList.toggle("hidden");
    header.querySelector(".group-chevron").textContent = open ? "▸" : "▾";
  });

  return tile;
}

function renderGroups(groups) {
  const grid = document.getElementById("group-grid");
  grid.innerHTML = "";
  groups.forEach(g => grid.appendChild(renderGroupTile(g)));
}

// ── Knockout bracket ──────────────────────────────────────────────────────────

function renderKnockout() {
  const bracket = document.getElementById("knockout-bracket");
  bracket.innerHTML = "";

  KNOCKOUT_ROUNDS.forEach(round => {
    const col = document.createElement("div");
    col.className = "bracket-col";

    const label = document.createElement("div");
    label.className = "bracket-round-label";
    label.textContent = round.label;
    col.appendChild(label);

    for (let i = 0; i < round.slots; i++) {
      const slot = document.createElement("div");
      slot.className = "bracket-slot empty";
      slot.innerHTML = `<span class="tbd">TBD</span><span class="vs-dot">vs</span><span class="tbd">TBD</span>`;
      col.appendChild(slot);
    }
    bracket.appendChild(col);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function initBracket() {
  const grid = document.getElementById("group-grid");
  grid.innerHTML = `<div class="bracket-loading">Loading matches…</div>`;

  try {
    const res = await fetch("/matches");
    const data = await res.json();
    renderGroups(data.groups || []);
  } catch (e) {
    grid.innerHTML = `<div class="bracket-loading error">Failed to load matches — is the server running?</div>`;
  }

  renderKnockout();
}

document.addEventListener("DOMContentLoaded", () => {
  initBracket();

  document.getElementById("knockout-toggle").addEventListener("click", () => {
    const bracket  = document.getElementById("knockout-bracket");
    const chevron  = document.getElementById("knockout-chevron");
    const expanded = !bracket.classList.contains("hidden");
    bracket.classList.toggle("hidden", expanded);
    chevron.textContent = expanded ? "▸" : "▾";
  });
});
