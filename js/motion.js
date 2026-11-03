/**
 * motion.js — the animation engine. No libraries.
 *
 * Three tools:
 *   1. Spring   — physics-based value that chases a target (interruptible,
 *                 keeps its velocity when the target changes mid-flight).
 *   2. tween    — classic duration + easing curve animation.
 *   3. easings  — named easing functions (JS) and matching cubic-bezier strings (CSS).
 *
 * All active animations share ONE requestAnimationFrame loop (the "ticker"),
 * so 40 cards animating at once cost one rAF callback per frame, not 40.
 */

/* ================================================================== *
 * Reduced motion
 * ================================================================== */

const reducedQuery = window.matchMedia('(prefers-reduced-motion: reduce)');

/** True when the user asked the OS for less motion. Check it at call time (it can change). */
export const prefersReducedMotion = () => reducedQuery.matches;

export function onReducedMotionChange(callback) {
  reducedQuery.addEventListener('change', () => callback(reducedQuery.matches));
}

/* ================================================================== *
 * Easing library — every function maps t ∈ [0,1] → progress (may overshoot 1)
 * ================================================================== */

export const easings = {
  linear: (t) => t,
  easeInCubic: (t) => t * t * t,
  easeOutCubic: (t) => 1 - Math.pow(1 - t, 3),
  easeInOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  /** Fast start, very long gentle finish — great for counters and wipes. */
  easeOutExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  /** Slight overshoot past 1 then settles back. */
  easeOutBack: (t) => {
    const c1 = 1.70158;
    const c3 = c1 + 1;
    return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2);
  },
  /** Rubber-band wobble. */
  easeOutElastic: (t) => {
    if (t === 0 || t === 1) return t;
    const c4 = (2 * Math.PI) / 3;
    return Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * c4) + 1;
  },
};

/** CSS equivalents (also defined as variables in css/variables.css). */
export const cssEasings = {
  easeOutExpo: 'cubic-bezier(0.16, 1, 0.3, 1)',
  easeInOutCubic: 'cubic-bezier(0.65, 0, 0.35, 1)',
  easeOutBack: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
  easeInCubic: 'cubic-bezier(0.32, 0, 0.67, 0)',
};

/* ================================================================== *
 * Ticker — one shared rAF loop
 * ================================================================== */

const active = new Set(); // objects with a tick(dtSeconds, now) method returning true while still running
let rafId = 0;
let lastTime = 0;

function frame(now) {
  // Clamp dt: after a background tab or a long frame we don't want a huge jump.
  const dt = Math.min((now - lastTime) / 1000, 1 / 30);
  lastTime = now;
  for (const anim of [...active]) {
    if (!anim.tick(dt, now)) active.delete(anim);
  }
  rafId = active.size ? requestAnimationFrame(frame) : 0;
}

function schedule(anim) {
  active.add(anim);
  if (!rafId) {
    lastTime = performance.now();
    rafId = requestAnimationFrame(frame);
  }
}

/* ================================================================== *
 * Spring
 * ================================================================== */

/**
 * A damped spring:  force = −stiffness·(x − target) − damping·velocity
 *                   acceleration = force / mass
 *
 * Integrated with semi-implicit (symplectic) Euler in fixed 1/240 s sub-steps:
 *   v += a·h;  x += v·h
 * Updating v before x keeps the simulation stable even with stiff springs.
 *
 * Usage:
 *   const s = new Spring({ value: 0, stiffness: 200, damping: 20, onUpdate: (x) => … });
 *   s.to(1);        // animate to 1
 *   s.to(0.3);      // retarget mid-flight — velocity is preserved, no jump
 *   s.set(0);       // jump immediately (no animation)
 */
export class Spring {
  constructor({ value = 0, stiffness = 200, damping = 20, mass = 1, precision = 0.001, onUpdate, onDone } = {}) {
    this.value = value;
    this.target = value;
    this.velocity = 0;
    this.stiffness = stiffness;
    this.damping = damping;
    this.mass = mass;
    this.precision = precision;
    this.onUpdate = onUpdate;
    this.onDone = onDone;
    this.running = false;
    this._resolve = null;
  }

  /** Change spring parameters (e.g. switch to a bouncier spring for the return trip). */
  configure({ stiffness, damping, mass } = {}) {
    if (stiffness != null) this.stiffness = stiffness;
    if (damping != null) this.damping = damping;
    if (mass != null) this.mass = mass;
    return this;
  }

  /** Animate towards `target`. Returns a Promise that resolves when it settles. */
  to(target) {
    this.target = target;
    if (!this.running) {
      this.running = true;
      this.finished = new Promise((resolve) => (this._resolve = resolve));
      schedule(this);
    }
    return this.finished;
  }

  /** Jump to a value with no animation. */
  set(value) {
    this.value = this.target = value;
    this.velocity = 0;
    this.onUpdate?.(value, 0);
    this._settle();
  }

  stop() {
    this.target = this.value;
    this.velocity = 0;
    this._settle();
  }

  tick(dt) {
    if (!this.running) return false;
    const h = 1 / 240;
    let remaining = dt;
    while (remaining > 1e-6) {
      const step = Math.min(h, remaining);
      const force = -this.stiffness * (this.value - this.target) - this.damping * this.velocity;
      this.velocity += (force / this.mass) * step;
      this.value += this.velocity * step;
      remaining -= step;
    }
    const resting = Math.abs(this.velocity) < this.precision * 10 && Math.abs(this.value - this.target) < this.precision;
    if (resting) {
      this.value = this.target;
      this.velocity = 0;
    }
    this.onUpdate?.(this.value, this.velocity);
    if (resting) {
      this._settle();
      return false;
    }
    return true;
  }

  _settle() {
    if (!this.running) return;
    this.running = false;
    active.delete(this);
    this.onDone?.(this.value);
    this._resolve?.(this.value);
  }
}

/**
 * One-shot helper: spring(from, to, { stiffness, damping, mass, onUpdate, onDone }).
 * Returns the Spring, so you can call .to() on it later to interrupt / retarget.
 * With reduced motion it jumps straight to `to`.
 */
export function spring(from, to, options = {}) {
  const s = new Spring({ ...options, value: from });
  if (prefersReducedMotion() && options.respectReducedMotion !== false) {
    s.set(to);
    s.finished = Promise.resolve(to);
    options.onDone?.(to);
  } else {
    s.onUpdate?.(from, 0);
    s.to(to);
  }
  return s;
}

/* ================================================================== *
 * Tween
 * ================================================================== */

/**
 * tween({ from, to, duration, ease, delay, onUpdate, onDone })
 * Returns { cancel(), finished: Promise }.
 */
export function tween({ from = 0, to = 1, duration = 400, ease = easings.easeOutCubic, delay = 0, onUpdate, onDone } = {}) {
  let resolve;
  const finished = new Promise((r) => (resolve = r));
  if (prefersReducedMotion()) duration = Math.min(duration, 1);
  let start = null;
  const anim = {
    cancelled: false,
    tick(_dt, now) {
      if (this.cancelled) return false;
      if (start === null) start = now + delay;
      const t = duration <= 0 ? 1 : Math.min(1, Math.max(0, (now - start) / duration));
      onUpdate?.(from + (to - from) * ease(t), t);
      if (t >= 1) {
        onDone?.();
        resolve();
        return false;
      }
      return true;
    },
  };
  schedule(anim);
  return {
    cancel() {
      anim.cancelled = true;
      resolve();
    },
    finished,
  };
}

/* ================================================================== *
 * Small helpers used around the site
 * ================================================================== */

export const wait = (ms) => new Promise((r) => setTimeout(r, ms));
export const nextFrame = () => new Promise((r) => requestAnimationFrame(() => r()));

const numberTweens = new WeakMap();

/**
 * Count a number up inside an element: animateNumber(el, 4.3, { decimals: 1 }).
 * Starts from whatever the element currently shows, so repeated calls glide.
 */
export function animateNumber(el, to, { decimals = 0, duration = 1000, ease = easings.easeOutExpo } = {}) {
  numberTweens.get(el)?.cancel();
  const from = parseFloat(el.textContent) || 0;
  const format = (v) => v.toFixed(decimals);
  const tw = tween({ from, to, duration, ease, onUpdate: (v) => (el.textContent = format(v)) });
  numberTweens.set(el, tw);
  return tw.finished;
}

/** Stagger delay for the i-th item (capped so long lists don't take forever). */
export function staggerDelay(i, step, maxItems) {
  return Math.min(i, maxItems) * step;
}
