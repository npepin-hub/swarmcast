/**
 * p5.js Boids — one color per specialist role.
 *
 * Phase transitions (set via window.setSwarmPhase):
 *   idle → deliberating → critic → delphi → consensus
 *
 * Role assignment (set via window.assignRoles):
 *   Called when specialist list arrives; partitions boids into
 *   equal-sized groups, one per role, each with its own hue.
 */

const BOID_COUNT = 60;
const W = 860, H = 320;

// Built at runtime from the actual specialist list — one hue per slot,
// evenly distributed around the wheel so every group is visually distinct.
// Keyed by role name after assignRoles() is called.
const ROLE_HUES = {};
const DEFAULT_HUE = 55;

const PHASE_CONFIG = {
  idle:         { align: 0.02, cohesion: 0.01, separate: 0.15, speed: 1.2, chaos: 0.8 },
  deliberating: { align: 0.04, cohesion: 0.02, separate: 0.20, speed: 2.0, chaos: 1.4 },
  critic:       { align: 0.01, cohesion: 0.01, separate: 0.30, speed: 2.5, chaos: 2.0 },
  delphi:       { align: 0.20, cohesion: 0.10, separate: 0.18, speed: 1.8, chaos: 0.4 },
  consensus:    { align: 0.90, cohesion: 0.60, separate: 0.10, speed: 1.2, chaos: 0.0 },
};

let boids = [];
let phase = "idle";

class Boid {
  constructor(p, hue) {
    this.p    = p;
    this.pos  = p.createVector(p.random(W), p.random(H));
    this.vel  = p5.Vector.random2D().mult(p.random(1, 2));
    this.acc  = p.createVector(0, 0);
    this.maxSpeed = 3;
    this.maxForce = 0.08;
    this.hue  = hue;
    this.pulse = 0;   // frames remaining for vote-flash
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
    const RA = 60, RC = 100, RS = 28;

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
    if (cfg.chaos > 0) this.acc.add(p5.Vector.random2D().mult(cfg.chaos * 0.05));
  }

  update(cfg) {
    this.vel.add(this.acc).limit(this.maxSpeed * (cfg.speed / 2));
    this.pos.add(this.vel);
    this.acc.set(0, 0);
    if (this.pulse > 0) this.pulse--;
  }

  draw(p, cfg) {
    const angle  = this.vel.heading();
    const bright = this.pulse > 0 ? 255 : 210;
    const sat    = this.pulse > 0 ? 200 : 180;
    const alpha  = this.p.map(cfg.align, 0.02, 0.9, 140, 235);
    const scale  = this.pulse > 0 ? 1.5 : 1.0;

    p.push();
    p.translate(this.pos.x, this.pos.y);
    p.rotate(angle);
    p.scale(scale);
    p.noStroke();
    p.fill(this.hue, sat, bright, alpha);
    p.ellipse(0, 0, 22, 9);
    p.triangle(-10, 0, -19, -7, -19, 7);
    p.pop();
  }
}

new p5((p) => {
  p.setup = () => {
    const cnv = p.createCanvas(W, H);
    cnv.parent("boids-container");
    p.colorMode(p.HSB, 360, 255, 255, 255);
    // Default: all fish one color until roles are assigned
    for (let i = 0; i < BOID_COUNT; i++) boids.push(new Boid(p, DEFAULT_HUE));
  };

  p.draw = () => {
    const cfg = PHASE_CONFIG[phase] || PHASE_CONFIG.idle;
    p.background(15, 15, 25, 220);
    for (let b of boids) {
      b.flock(boids, cfg);
      b.update(cfg);
      b.edges();
      b.draw(p, cfg);
    }
  };
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

/**
 * Partition boids into equal groups, one per role.
 * Hues are generated dynamically — evenly spaced around the colour wheel,
 * offset by 30° so we never start at pure red (which looks like an error state).
 * specialists: [{ role, system_prompt, data_slice_id }, ...]
 */
window.assignRoles = (specialists) => {
  if (!specialists || specialists.length === 0) return;

  const n   = specialists.length;
  const step = 360 / n;

  // Clear and rebuild the hue map for this run
  Object.keys(ROLE_HUES).forEach(k => delete ROLE_HUES[k]);
  specialists.forEach((s, idx) => {
    ROLE_HUES[s.role] = Math.round((30 + idx * step) % 360);
  });

  // Assign boid groups
  const groupSize = Math.floor(BOID_COUNT / n);
  specialists.forEach((s, idx) => {
    const hue   = ROLE_HUES[s.role];
    const start = idx * groupSize;
    const end   = idx === n - 1 ? BOID_COUNT : start + groupSize;
    for (let i = start; i < end; i++) {
      if (boids[i]) { boids[i].hue = hue; boids[i].role = s.role; }
    }
  });
};

/**
 * Flash the boids belonging to a role when their vote arrives.
 * role: string matching specialist role name
 */
window.pulseRole = (role) => {
  for (let b of boids) {
    if (b.role === role) b.pulse = 18;
  }
};

// Legend: exposed so ws.js can render a DOM legend
window.ROLE_HUES = ROLE_HUES;
