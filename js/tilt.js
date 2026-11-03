/**
 * tilt.js — reusable 3D parallax tilt for cards.
 *
 * Expected markup (only [data-tilt-inner] is required):
 *
 *   <article class="card">                  ← receives pointer events
 *     <div data-tilt-shadow></div>          ← drop shadow, slides opposite to the tilt
 *     <div data-tilt-inner>                 ← rotates in 3D (transform-style: preserve-3d)
 *       <div class="cover">
 *         <img data-tilt-image>             ← artwork, slides slightly inside its frame
 *       </div>
 *       <div class="frame">…</div>          ← lifted with translateZ in CSS → depth parallax
 *       <div class="glare-clip"><div data-tilt-glare></div></div>   ← moving highlight
 *     </div>
 *   </article>
 *
 * Only `transform` and `opacity` are written, once per frame, through the shared
 * spring ticker in motion.js — no layout work while the pointer moves.
 *
 *   const tilt = attachTilt(cardEl, { maxTilt: 15 });
 *   tilt.destroy();   // when the card is removed
 */

import { TILT, MOTION } from './config.js';
import { Spring, prefersReducedMotion } from './motion.js';

const instances = new Set();
const clamp = (v, min = -1, max = 1) => Math.min(max, Math.max(min, v));

export function attachTilt(card, userOptions = {}) {
  const opt = { ...TILT, ...userOptions };
  const inner = card.querySelector('[data-tilt-inner]');
  if (!inner) return { destroy() {} };
  const image = card.querySelector('[data-tilt-image]');
  const glare = card.querySelector('[data-tilt-glare]');
  const shadow = card.querySelector('[data-tilt-shadow]');

  let rect = null; // cached card rectangle (read once per hover, not per move)
  let pressed = false;
  let hovering = false;

  /* Three springs: pointer x, pointer y (both −1…1) and "lift" (0 = resting, 1 = hovered). */
  const follow = MOTION.springs.tiltFollow;
  const sx = new Spring({ ...follow, precision: 0.0005, onUpdate: render });
  const sy = new Spring({ ...follow, precision: 0.0005, onUpdate: render });
  const lift = new Spring({ ...follow, precision: 0.0005, onUpdate: render });

  // Coalesce: the three springs each call render() in the same frame; only write once.
  let renderQueued = false;
  function render() {
    if (renderQueued) return;
    renderQueued = true;
    queueMicrotask(write);
  }

  function write() {
    renderQueued = false;
    const x = sx.value;
    const y = sy.value;
    const l = lift.value;
    const s = 1 + (opt.scale - 1) * l;
    // Pointer on the right (x>0) pushes the right edge away → rotateY(+).
    // Pointer at the top (y<0) pushes the top edge away → rotateX(+).
    inner.style.transform =
      `perspective(${opt.perspective}px) rotateX(${(-y * opt.maxTilt).toFixed(3)}deg) ` +
      `rotateY(${(x * opt.maxTilt).toFixed(3)}deg) scale3d(${s}, ${s}, 1)`;
    if (image) {
      image.style.transform = `translate3d(${(-x * opt.imageShift).toFixed(2)}px, ${(-y * opt.imageShift).toFixed(2)}px, 0) scale(1.08)`;
    }
    if (glare) {
      glare.style.transform = `translate3d(${(x * 30).toFixed(2)}%, ${(y * 30).toFixed(2)}%, 0)`;
      glare.style.opacity = (opt.glare * clamp(l, 0, 1.2) * (0.55 + 0.45 * Math.hypot(x, y))).toFixed(3);
    }
    if (shadow) {
      shadow.style.transform =
        `translate3d(${(-x * opt.shadowShift).toFixed(2)}px, ${(-y * opt.shadowShift + l * 10).toFixed(2)}px, 0) ` +
        `scale(${(0.94 + 0.06 * l).toFixed(3)})`;
      shadow.style.opacity = (0.45 + 0.4 * clamp(l, 0, 1)).toFixed(3);
    }
  }

  const useFollow = () => [sx, sy, lift].forEach((s) => s.configure(MOTION.springs.tiltFollow));
  const useReturn = () => [sx, sy, lift].forEach((s) => s.configure(MOTION.springs.tiltReturn));

  function pointerTo(e, strength = 1) {
    if (!rect) rect = card.getBoundingClientRect();
    const nx = clamp(((e.clientX - rect.left) / rect.width) * 2 - 1);
    const ny = clamp(((e.clientY - rect.top) / rect.height) * 2 - 1);
    sx.to(nx * strength);
    sy.to(ny * strength);
  }

  function reset() {
    hovering = pressed = false;
    rect = null;
    useReturn(); // bouncier spring for the trip home
    sx.to(0);
    sy.to(0);
    lift.to(0);
    card.classList.remove('is-tilting');
  }

  /* ---------------- mouse / pen: hover ---------------- */
  function onEnter(e) {
    if (e.pointerType === 'touch' || prefersReducedMotion()) return;
    hovering = true;
    rect = card.getBoundingClientRect();
    useFollow();
    lift.to(1);
    card.classList.add('is-tilting');
    pointerTo(e);
  }
  function onMove(e) {
    if (prefersReducedMotion()) return;
    if (e.pointerType === 'touch') {
      if (pressed) pointerTo(e, opt.touchFactor);
      return;
    }
    if (!hovering) onEnter(e);
    else pointerTo(e);
  }
  function onLeave(e) {
    if (e.pointerType === 'touch' && !pressed) return;
    reset();
  }

  /* ---------------- touch: gentle tilt while pressing ---------------- */
  function onDown(e) {
    if (e.pointerType !== 'touch' || prefersReducedMotion()) return;
    pressed = true;
    rect = card.getBoundingClientRect();
    useFollow();
    lift.to(opt.pressScale < 1 ? -(1 - opt.pressScale) / (opt.scale - 1) : 0.5); // negative lift = slight press-in
    pointerTo(e, opt.touchFactor);
  }
  function onUp(e) {
    if (e.pointerType === 'touch') reset();
  }

  // If the page scrolls while hovering, the cached rect is stale.
  const onScroll = () => (rect = null);

  card.addEventListener('pointerenter', onEnter);
  card.addEventListener('pointermove', onMove);
  card.addEventListener('pointerleave', onLeave);
  card.addEventListener('pointerdown', onDown);
  card.addEventListener('pointerup', onUp);
  card.addEventListener('pointercancel', onUp); // fired when the touch turns into a scroll
  window.addEventListener('scroll', onScroll, { passive: true });

  const instance = {
    card,
    /** Used by device-orientation mode. x, y in −1…1. */
    orient(x, y) {
      if (hovering || pressed || prefersReducedMotion()) return;
      useFollow();
      sx.to(x);
      sy.to(y);
    },
    destroy() {
      card.removeEventListener('pointerenter', onEnter);
      card.removeEventListener('pointermove', onMove);
      card.removeEventListener('pointerleave', onLeave);
      card.removeEventListener('pointerdown', onDown);
      card.removeEventListener('pointerup', onUp);
      card.removeEventListener('pointercancel', onUp);
      window.removeEventListener('scroll', onScroll);
      [sx, sy, lift].forEach((s) => s.stop());
      instances.delete(instance);
      visibleCards.delete(card);
      orientObserver?.unobserve(card);
    },
  };
  instances.add(instance);
  orientObserver?.observe(card);
  return instance;
}

/* ================================================================== *
 * Optional: tilt cards with the phone's gyroscope.
 * Enabled with "deviceTilt": true in data/settings.json.
 * Only cards currently on screen are animated.
 * ================================================================== */

const visibleCards = new Set();
let orientObserver = null;

export function enableDeviceTilt() {
  const coarse = window.matchMedia('(hover: none) and (pointer: coarse)').matches;
  if (!coarse || !('DeviceOrientationEvent' in window) || orientObserver) return;

  orientObserver = new IntersectionObserver((records) => {
    records.forEach((r) => (r.isIntersecting ? visibleCards.add(r.target) : visibleCards.delete(r.target)));
  });
  instances.forEach((i) => orientObserver.observe(i.card));

  let queued = null;
  const onOrient = (e) => {
    if (e.gamma == null || e.beta == null) return;
    // gamma: left/right tilt (−90…90). beta: front/back (≈45° when holding a phone).
    queued = { x: clamp(e.gamma / 30) * 0.6, y: clamp((e.beta - 45) / 30) * 0.6 };
    requestAnimationFrame(() => {
      if (!queued) return;
      const { x, y } = queued;
      queued = null;
      instances.forEach((i) => visibleCards.has(i.card) && i.orient(x, y));
    });
  };

  const start = () => window.addEventListener('deviceorientation', onOrient);
  // iOS 13+ needs permission, which can only be requested from a tap.
  if (typeof DeviceOrientationEvent.requestPermission === 'function') {
    const ask = () => {
      DeviceOrientationEvent.requestPermission().then((state) => state === 'granted' && start()).catch(() => {});
    };
    window.addEventListener('pointerup', ask, { once: true });
  } else {
    start();
  }
}
