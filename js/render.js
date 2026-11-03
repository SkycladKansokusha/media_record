/**
 * render.js — functions that turn data into DOM elements.
 *
 * Everything is built with the tiny h() helper below instead of innerHTML.
 * That way text from your JSON can never be interpreted as HTML (safe),
 * and the structure reads like the markup it produces.
 */

import { STRINGS, t } from './strings.js';
import { displayTitles, guessLang } from './store.js';

/* ================================================================== *
 * h(tag, attributes, ...children)
 *   h('p', { class: 'x', lang: 'ja' }, 'text', h('span', {}, 'child'))
 *   - attributes starting with "on" become event listeners (onclick → click)
 *   - `dataset: {a: 1}` sets data-a="1"; `style: {…}` sets inline styles
 *   - null / false / undefined attributes and children are skipped
 * ================================================================== */
export function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key === 'class') el.className = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  appendChildren(el, children);
  return el;
}

function appendChildren(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
}

/** Build SVG elements (they need a namespace). */
const SVG_NS = 'http://www.w3.org/2000/svg';
export function svg(tag, attrs = {}, ...children) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [key, value] of Object.entries(attrs)) if (value != null) el.setAttribute(key, value);
  children.flat().forEach((c) => c && el.append(c));
  return el;
}

/* ================================================================== *
 * Formatting
 * ================================================================== */

const dateFormat = new Intl.DateTimeFormat('en-GB', { day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC' });

/** "2026-10-20" → "20 OCT 2026" */
export function formatDate(iso) {
  const time = Date.parse(`${iso}T00:00:00Z`);
  if (!iso || Number.isNaN(time)) return STRINGS.stats.none;
  return dateFormat
    .formatToParts(time)
    .map((p) => (p.type === 'month' ? p.value.slice(0, 3) : p.value)) // en-GB may print "Sept"
    .join('')
    .replace(/\./g, '')
    .toUpperCase();
}

export const formatRating = (n) => (Number.isInteger(n) ? n.toFixed(1) : String(n));

/* ================================================================== *
 * Rating — diamonds instead of stars, supports half values
 * ================================================================== */

const DIAMOND = 'M6 0.9 L11.1 6 L6 11.1 L0.9 6 Z';
const HALF_DIAMOND = 'M6 0.9 L6 11.1 L0.9 6 Z';

/**
 * <span class="rating" role="img" aria-label="Rated 4.5 out of 5">◆◆◆◆◈</span>
 * Each diamond gets --i (its index) so CSS can stagger the "light-up" animation.
 */
export function ratingDiamonds(value, { size = 'sm' } = {}) {
  const diamonds = [];
  for (let i = 0; i < 5; i++) {
    const fill = Math.max(0, Math.min(1, value - i)); // 1, 0.5 or 0
    const state = fill >= 1 ? 'full' : fill >= 0.5 ? 'half' : 'empty';
    diamonds.push(
      svg(
        'svg',
        { class: `diamond diamond--${state}`, viewBox: '0 0 12 12', 'aria-hidden': 'true', style: `--i:${i}` },
        svg('path', { class: 'diamond__track', d: DIAMOND }),
        state !== 'empty' && svg('path', { class: 'diamond__fill', d: state === 'full' ? DIAMOND : HALF_DIAMOND }),
      ),
    );
  }
  return h('span', { class: `rating rating--${size}`, role: 'img', 'aria-label': t(STRINGS.rating.aria, { n: formatRating(value) }) }, diamonds);
}

/* ================================================================== *
 * Covers
 * ================================================================== */

/** Stable 0…1 number from a string (used to vary placeholder patterns). */
function hash01(str) {
  let x = 2166136261;
  for (let i = 0; i < str.length; i++) x = Math.imul(x ^ str.charCodeAt(i), 16777619);
  return ((x >>> 0) % 1000) / 1000;
}

/** First visible character of the title (fallback: original title). */
function initialOf(entry) {
  const source = entry.title || entry.originalTitle || '?';
  return { char: Array.from(source.trim())[0] || '?', lang: entry.title === entry.originalTitle ? entry.originalLanguage : guessLang(source) || 'en' };
}

/** CSS-only placeholder: navy panel, grid, big initial, file code. */
export function placeholderCover(entry) {
  const { char, lang } = initialOf(entry);
  const seed = hash01(entry.id);
  return h(
    'div',
    { class: 'placeholder', style: { '--seed': seed.toFixed(3), '--angle': `${Math.round(seed * 60) - 30}deg` }, 'aria-hidden': 'true' },
    h('span', { class: 'placeholder__char', lang }, char),
    h('span', { class: 'placeholder__label' }, STRINGS.card.noCover),
    h('span', { class: 'placeholder__code' }, STRINGS.categoryCodes[entry._category]),
  );
}

/** <img> if the entry has a cover; falls back to the placeholder if the file fails to load. */
export function coverArt(entry, { lazy = true, tiltImage = false } = {}) {
  if (!entry.cover) return placeholderCover(entry);
  const img = h('img', {
    class: 'cover__img',
    src: entry.cover,
    alt: '',
    loading: lazy ? 'lazy' : 'eager',
    decoding: 'async',
    'data-tilt-image': tiltImage || null,
  });
  img.addEventListener('error', () => img.replaceWith(placeholderCover(entry)), { once: true });
  return img;
}

/* ================================================================== *
 * Titles
 * ================================================================== */

/** Main title + optional smaller original title, following settings.titleMode. */
export function titleBlock(entry, mode, { tag = 'h3', cls = 'card' } = {}) {
  const { primary, secondary } = displayTitles(entry, mode);
  return [
    h(tag, { class: `${cls}__title`, lang: primary.lang || null }, primary.text),
    secondary && h('p', { class: `${cls}__orig`, lang: secondary.lang || null }, secondary.text),
  ];
}

/* ================================================================== *
 * Card
 * ================================================================== */

/**
 * One card. Layer order (back → front):
 *   shadow · cover (artwork) · frame (corner marks + labels) · glare
 * The whole card is clickable via the transparent .card__hit button,
 * which keeps the heading semantic and the button accessible.
 */
export function createCard(entry, { mode, onOpen }) {
  const { primary } = displayTitles(entry, mode);
  const cover = h('div', { class: 'card__cover' }, coverArt(entry, { tiltImage: true }));

  const card = h(
    'article',
    { class: 'card', dataset: { id: entry.id } },
    h(
      'div',
      { class: 'card__stage' },
      h('div', { class: 'card__shadow', 'data-tilt-shadow': '' }),
      h(
        'div',
        { class: 'card__tilt', 'data-tilt-inner': '' },
        cover,
        h(
          'div',
          { class: 'card__frame', 'aria-hidden': 'true' },
          h('span', { class: 'corner corner--tl' }),
          h('span', { class: 'corner corner--tr' }),
          h('span', { class: 'corner corner--bl' }),
          h('span', { class: 'corner corner--br' }),
          h('span', { class: 'card__file' }, t(STRINGS.card.file, { n: entry._fileNo })),
          h('span', { class: 'card__score' }, formatRating(entry.rating)),
        ),
        h('div', { class: 'card__glare-clip', 'aria-hidden': 'true' }, h('div', { class: 'card__glare', 'data-tilt-glare': '' })),
      ),
    ),
    h(
      'div',
      { class: 'card__meta' },
      titleBlock(entry, mode),
      h(
        'p',
        { class: 'card__sub' },
        entry.creator && h('span', { class: 'card__creator' }, entry.creator),
        entry.year && h('span', { class: 'card__year' }, entry.year),
      ),
      ratingDiamonds(entry.rating),
    ),
    h('button', {
      class: 'card__hit',
      type: 'button',
      'aria-label': t(STRINGS.card.open, { title: primary.text }),
      onclick: () => onOpen(entry, card),
    }),
  );
  return card;
}

/* ================================================================== *
 * Empty / error states
 * ================================================================== */

export function emptyState({ isCategoryEmpty, onReset }) {
  return h(
    'div',
    { class: 'state' },
    h('span', { class: 'state__mark', 'aria-hidden': 'true' }),
    h('p', { class: 'state__title' }, isCategoryEmpty ? STRINGS.empty.categoryTitle : STRINGS.empty.title),
    h('p', { class: 'state__hint' }, isCategoryEmpty ? STRINGS.empty.categoryHint : STRINGS.empty.hint),
    !isCategoryEmpty && h('button', { class: 'btn', type: 'button', onclick: onReset }, STRINGS.empty.reset),
  );
}

export function errorState({ file, onRetry }) {
  return h(
    'div',
    { class: 'state state--error', role: 'alert' },
    h('span', { class: 'state__mark', 'aria-hidden': 'true' }),
    h('p', { class: 'state__title' }, STRINGS.error.title),
    h('p', { class: 'state__hint' }, t(STRINGS.error.hint, { file })),
    h('button', { class: 'btn', type: 'button', onclick: onRetry }, STRINGS.error.retry),
  );
}
