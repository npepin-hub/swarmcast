/**
 * p5.js — one fish per specialist agent.
 * Each fish carries a speech bubble showing its role + area of focus.
 * Phase drives flocking behaviour (chaos → alignment → lock).
 */

const W = 860, H = 320;

const PHASE_CONFIG = {
  idle:         { align: 0.05, cohesion: 0.03, separate: 0.35, speed: 1.8, chaos: 1.0 },
  deliberating: { align: 0.04, cohesion: 0.02, separate: 0.45, speed: 3.2, chaos: 2.4 },
  critic:       { align: 0.01, cohesion: 0.01, separate: 0.55, speed: 3.8, chaos: 3.2 },
  delphi:       { align: 0.35, cohesion: 0.25, separate: 0.30, speed: 2.4, chaos: 0.6 },
  consensus:    { align: 0.92, cohesion: 0.65, separate: 0.12, speed: 1.4, chaos: 0.0 },
};

// Focus descriptors per role — shown in the speech bubble subtitle
const ROLE_FOCUS = {
  tactical_analyst:   "xG · formations · pressing",
  historical_stats:   "WC history · H2H · base rates",
  current_form:       "last 5 results · momentum",
  squad_fitness:      "injuries · suspensions · depth",
  tournament_context: "standings · venue · incentives",
  contrarian:         "underdog case · upset risk",
};

// Fixed palette — no purple
const HUE_PALETTE = [0, 22, 48, 80, 145, 175, 200, 225, 355];
const ROLE_HUES   = {};
const DEFAULT_HUE = 55;

let boids = [];
let phase = "idle";

class Boid {
  constructor(p, hue, role, focus) {
    this.p        = p;
    this.pos      = p.createVector(p.random(W), p.random(H));
    this.vel      = p5.Vector.random2D().mult(p.random(2, 5));
    this.acc      = p.createVector(0, 0);
    this.maxSpeed = p.random(3.5, 6.0);    // each fish has its own top speed
    this.maxForce = p.random(0.12, 0.24);  // each fish turns at a different rate
    this.hue      = hue + p.random(-12, 12);  // slight colour drift within school
    this.role     = role;
    this.focus    = focus;
    this.pulse    = 0;
    this.size     = p.random(0.7, 1.4);
    this.wander   = p.random(0, Math.PI * 2);  // individual wander offset
    this.wanderSpd= p.random(0.02, 0.06);      // how fast each fish wanders
  }

  edges() {
    if (this.pos.x > W) this.pos.x = 0;
    else if (this.pos.x < 0) this.pos.x = W;
    if (this.pos.y > H) this.pos.y = 0;
    else if (this.pos.y < 0) this.pos.y = H;
  }

  flock(all, cfg) {
    let align = this.p.createVector();
    let cohes = this.p.createVector();
    let sep   = this.p.createVector();
    let ac = 0, cc = 0, sc = 0;
    const RA = 120, RC = 180, RS = 55;

    for (let o of all) {
      if (o === this) continue;
      const d = p5.Vector.dist(this.pos, o.pos);
      if (d < RA) { align.add(o.vel); ac++; }
      if (d < RC) { cohes.add(o.pos); cc++; }
      if (d < RS) { sep.add(p5.Vector.sub(this.pos, o.pos).div(d)); sc++; }
    }

    if (ac) align.div(ac).setMag(this.maxSpeed).sub(this.vel).limit(this.maxForce);
    if (cc) {
      cohes.div(cc);
      cohes = p5.Vector.sub(cohes, this.pos).setMag(this.maxSpeed).sub(this.vel).limit(this.maxForce);
    }
    if (sc) sep.div(sc).setMag(this.maxSpeed).sub(this.vel).limit(this.maxForce);

    this.acc.add(align.mult(cfg.align));
    this.acc.add(cohes.mult(cfg.cohesion));
    this.acc.add(sep.mult(cfg.separate));
    if (cfg.chaos > 0) this.acc.add(p5.Vector.random2D().mult(cfg.chaos * 0.06));
  }

  update(cfg) {
    // Per-fish wander: a gentle sinusoidal drift unique to each fish
    this.wander += this.wanderSpd;
    const wanderForce = cfg.chaos > 0
      ? p5.Vector.fromAngle(this.wander).mult(cfg.chaos * 0.04)
      : p5.Vector.fromAngle(this.wander).mult(0.008);
    this.acc.add(wanderForce);

    this.vel.add(this.acc).limit(this.maxSpeed * (cfg.speed / 2));
    this.pos.add(this.vel);
    this.acc.set(0, 0);
    if (this.pulse > 0) this.pulse--;
  }

  drawFish(p, cfg) {
    const angle  = this.vel.heading();
    const bright = this.pulse > 0 ? 255 : 215;
    const sat    = this.pulse > 0 ? 220 : 190;
    const alpha  = p.map(cfg.align, 0.02, 0.95, 150, 240);
    const scale  = (this.pulse > 0 ? 1.6 : 1.0) * this.size;

    p.push();
    p.translate(this.pos.x, this.pos.y);
    p.rotate(angle);
    p.scale(scale);
    p.noStroke();
    p.fill(this.hue, sat, bright, alpha);
    p.ellipse(0, 0, 28, 12);
    p.triangle(-13, 0, -24, -9, -24, 9);
    p.pop();
  }

}

new p5((p) => {
  p.setup = () => {
    const cnv = p.createCanvas(W, H);
    cnv.parent("boids-container");
    p.colorMode(p.HSB, 360, 255, 255, 255);
    window._p5Instance = p;  // expose so assignRoles can construct Boids
  };

  p.draw = () => {
    const cfg = PHASE_CONFIG[phase] || PHASE_CONFIG.idle;
    p.background(15, 15, 25, 220);
    for (let b of boids) {
      b.flock(boids, cfg);
      b.update(cfg);
      b.edges();
      b.drawFish(p, cfg);
    }
    // One bubble per role at the centroid of that role's group
    if (phase !== "idle") drawGroupBubbles(p);
  };

  function drawGroupBubbles(p) {
    const centroids = {};
    const counts    = {};
    for (let b of boids) {
      if (!b.role) continue;
      if (!centroids[b.role]) { centroids[b.role] = { x: 0, y: 0, hue: b.hue, focus: b.focus }; counts[b.role] = 0; }
      centroids[b.role].x += b.pos.x;
      centroids[b.role].y += b.pos.y;
      counts[b.role]++;
    }
    for (const role of Object.keys(centroids)) {
      const n   = counts[role];
      const cx  = centroids[role].x / n;
      const cy  = centroids[role].y / n;
      const hue = centroids[role].hue;
      const roleLine  = role.replace(/_/g, " ");
      const focusLine = centroids[role].focus || "";

      p.textFont("system-ui, sans-serif");
      p.textSize(10);
      const rw = p.textWidth(roleLine);
      p.textSize(8.5);
      const fw = p.textWidth(focusLine);
      const bw = Math.max(rw, fw) + 16;
      const bh = 34;
      const bx = p.constrain(cx, bw / 2 + 6, W - bw / 2 - 6);
      const by = p.constrain(cy - 38, bh + 4, H - 10);

      p.colorMode(p.HSB, 360, 255, 255, 255);
      p.noStroke();
      p.fill(hue, 140, 40, 210);
      p.rect(bx - bw / 2, by - bh, bw, bh, 5);
      p.triangle(bx - 5, by, bx + 5, by, bx, by + 8);

      p.fill(hue, 60, 255, 245);
      p.textSize(10);
      p.textStyle(p.BOLD);
      p.textAlign(p.CENTER, p.TOP);
      p.text(roleLine, bx, by - bh + 5);

      p.fill(hue, 80, 200, 200);
      p.textSize(8.5);
      p.textStyle(p.NORMAL);
      p.text(focusLine, bx, by - bh + 18);
      p.textAlign(p.LEFT, p.BASELINE);
    }
  }
});

// ── External API ──────────────────────────────────────────────────────────────

window.setSwarmPhase = (newPhase) => {
  if (!PHASE_CONFIG[newPhase]) return;
  phase = newPhase;
  const labels = {
    idle:         "Waiting for match...",
    deliberating: "Agents deliberating independently...",
    critic:       "Holistic critic firing...",
    delphi:       "Delphi round — consensus emerging...",
    consensus:    "Consensus locked.",
  };
  const el = document.getElementById("phase-label");
  if (el) el.textContent = labels[newPhase] || newPhase;
};

window.assignRoles = (specialists) => {
  if (!specialists || specialists.length === 0) return;

  Object.keys(ROLE_HUES).forEach(k => delete ROLE_HUES[k]);
  specialists.forEach((s, idx) => {
    ROLE_HUES[s.role] = HUE_PALETTE[idx % HUE_PALETTE.length];
  });

  // 25 fish per specialist — bubble drawn at group centroid
  const FISH_PER_ROLE = 25;
  boids = specialists.flatMap((s) => {
    const hue   = ROLE_HUES[s.role];
    const focus = s.focus || ROLE_FOCUS[s.role] || s.role.replace(/_/g, " ");
    return Array.from({ length: FISH_PER_ROLE }, () =>
      new Boid(window._p5Instance, hue, s.role, focus)
    );
  });
};

window.pulseRole = (role) => {
  for (let b of boids) { if (b.role === role) b.pulse = 22; }
};

window.ROLE_HUES = ROLE_HUES;
