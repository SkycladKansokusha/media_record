/**
 * detail.js — the detail panel (a native <dialog>).
 *
 * Opening uses the FLIP technique:
 *   First  — measure where the clicked card's cover is on screen
 *   Last   — lay out the panel, measure where its big cover ends up
 *   Invert — transform the big cover so it sits exactly on top of the small one
 *   Play   — spring the transform back to "none"; it appears to grow out of the card
 * Closing plays the same thing backwards.
 *
 * <dialog>.showModal() gives us focus trapping, Esc to close and inert background for free.
 */

import { STRINGS, t } from './strings.js';
import { MOTION } from './config.js';
import { Spring, prefersReducedMotion } from './motion.js';
import { h, coverArt, ratingDiamonds, formatDate, formatRating, titleBlock } from './render.js';
import { displayCreator, guessLang, sameTitle } from './store.js';

let dialog, backdrop, panel, coverEl, body;
let sourceCard = null;
let progress = null; // Spring 0 (at card) → 1 (in panel)
let flip = null; // { dx, dy, sx, sy }
let closing = false;
let lastFocus = null;

/** Create the (empty) dialog once at startup. */
export function initDetail() {
  backdrop = h('div', { class: 'detail__backdrop', onclick: () => closeDetail() });
  coverEl = h('div', { class: 'detail__cover' });
  body = h('div', { class: 'detail__body' });
  panel = h(
    'div',
    { class: 'detail__panel' },
    // Wrapper only matters on phones (sticky bar); on desktop it is display: contents.
    h(
      'div',
      { class: 'detail__topbar' },
      h(
        'button',
        { class: 'detail__close', type: 'button', 'aria-label': STRINGS.detail.closeAria, onclick: () => closeDetail() },
        h('span', { class: 'detail__close-x', 'aria-hidden': 'true' }),
        h('span', { class: 'detail__close-text' }, STRINGS.detail.close),
      ),
    ),
    h('div', { class: 'detail__grid' }, h('div', { class: 'detail__cover-col' }, coverEl), body),
  );
  dialog = h('dialog', { class: 'detail', 'aria-label': STRINGS.detail.dialogLabel }, backdrop, panel);

  // Esc key: run our closing animation instead of the instant default close.
  dialog.addEventListener('cancel', (e) => {
    e.preventDefault();
    closeDetail();
  });
  document.body.append(dialog);

  progress = new Spring({ ...MOTION.springs.panel, precision: 0.0008, onUpdate: renderFlip });
}

/** Apply the FLIP transform for spring value p (0 = over the card, 1 = final spot). */
function renderFlip(p) {
  const clamped = Math.min(1, Math.max(0, p));
  backdrop.style.opacity = clamped.toFixed(3);
  if (!flip) {
    coverEl.style.transform = '';
    return;
  }
  const q = 1 - p;
  const sx = flip.sx + (1 - flip.sx) * p;
  const sy = flip.sy + (1 - flip.sy) * p;
  coverEl.style.transform = `translate3d(${(flip.dx * q).toFixed(2)}px, ${(flip.dy * q).toFixed(2)}px, 0) scale(${sx.toFixed(4)}, ${sy.toFixed(4)})`;
}

/** Measure source (card cover) vs. target (panel cover). */
function measureFlip() {
  const src = sourceCard?.isConnected ? sourceCard.querySelector('.card__cover') : null;
  if (!src) return null;
  const a = src.getBoundingClientRect();
  const saved = coverEl.style.transform;
  coverEl.style.transform = ''; // measure the untransformed final position
  const b = coverEl.getBoundingClientRect();
  coverEl.style.transform = saved;
  if (!a.width || !b.width) return null;
  // If the card is scrolled far off-screen, a fly-in from there looks odd — just fade.
  if (a.bottom < -a.height || a.top > innerHeight + a.height) return null;
  return { dx: a.left - b.left, dy: a.top - b.top, sx: a.width / b.width, sy: a.height / b.height };
}

/* ------------------------------------------------------------------ */

function field(label, ...content) {
  return h('div', { class: 'detail__field' }, h('dt', { class: 'label' }, label), h('dd', {}, ...content));
}

function buildBody(entry, { mode, categoryLabel, onTag }) {
  const creator = displayCreator(entry);
  const showOriginalField = Boolean(entry.originalTitle) && !sameTitle(entry.originalTitle, entry.title);
  const hasYear = entry.year != null && entry.year !== '';

  // Three fixed rows, two columns each. A missing cell is null and gets filtered out,
  // so the remaining cell moves left within its own row and an empty row disappears.
  const rows = [
    [
      showOriginalField
        ? field(STRINGS.detail.originalTitle, h('span', { lang: entry.originalLanguage || guessLang(entry.originalTitle) || null }, entry.originalTitle))
        : null,
      entry.altTitles?.length > 0
        ? field(STRINGS.detail.alsoKnownAs, h('ul', { class: 'detail__aka' }, entry.altTitles.map((alt) => h('li', { lang: guessLang(alt) || null }, alt))))
        : null,
    ],
    [
      creator.primary
        ? field(
            STRINGS.detail.creator[entry._category],
            h('span', {}, creator.primary),
            creator.secondary ? h('span', { class: 'detail__muted', lang: creator.secondaryLang || null }, creator.secondary) : null,
          )
        : null,
      hasYear ? field(STRINGS.detail.year, h('span', { class: 'mono' }, entry.year)) : null,
    ],
    [
      entry.date ? field(STRINGS.detail.date, h('span', { class: 'mono' }, formatDate(entry.date))) : null,
      entry.tags?.length > 0
        ? field(
            STRINGS.detail.tags,
            h(
              'ul',
              { class: 'detail__tags' },
              entry.tags.map((tag) => h('li', {}, h('button', { class: 'chip', type: 'button', lang: guessLang(tag) || null, onclick: () => onTag(tag) }, tag))),
            ),
          )
        : null,
    ],
  ]
    .map((cells) => cells.filter(Boolean))
    .filter((cells) => cells.length > 0)
    .map((cells) => h('dl', { class: 'detail__row' }, cells));

  return [
    h('p', { class: 'detail__file label' }, `${t(STRINGS.detail.file, { n: entry._fileNo })}  //  ${categoryLabel}`),
    titleBlock(entry, mode, { tag: 'h2', cls: 'detail' }),
    h('div', { class: 'detail__wire', 'aria-hidden': 'true' }),
    h(
      'div',
      { class: 'detail__rating' },
      h('span', { class: 'label' }, STRINGS.detail.rating),
      h('span', { class: 'detail__score' }, formatRating(entry.rating)),
      ratingDiamonds(entry.rating, { size: 'lg' }),
    ),
    h(
      'section',
      { class: 'detail__review' },
      h('h3', { class: 'label' }, STRINGS.detail.review),
      entry.review
        ? h('p', { class: 'detail__review-text', lang: guessLang(entry.review) || null }, entry.review)
        : h('p', { class: 'detail__muted' }, STRINGS.detail.noReview),
    ),
    rows.length > 0 ? h('div', { class: 'detail__fields' }, rows) : null,
  ];
}

/* ------------------------------------------------------------------ */

/**
 * @param entry  the entry object
 * @param card   the clicked card element (animation origin)
 * @param ctx    { mode, categoryLabel, aspect, onTag(tag) }
 */
export function openDetail(entry, card, ctx) {
  if (dialog.open) return;
  closing = false;
  sourceCard = card;
  lastFocus = document.activeElement;

  dialog.dataset.aspect = ctx.aspect;
  coverEl.replaceChildren(coverArt(entry, { lazy: false }));
  const parts = buildBody(entry, {
    ...ctx,
    onTag: (tag) => closeDetail().then(() => ctx.onTag(tag)),
  });
  body.replaceChildren(...parts.flat().filter(Boolean)); // titleBlock() returns an array
  dialog.scrollTop = 0; // the dialog is the scroll container (see components.css)

  document.documentElement.classList.add('has-modal'); // locks page scroll
  dialog.showModal();
  dialog.classList.remove('is-closing');
  dialog.classList.add('is-open');
  dialog.querySelector('.detail__close').focus({ preventScroll: true });

  if (prefersReducedMotion()) {
    flip = null;
    progress.set(1);
    return;
  }
  flip = measureFlip();
  card.classList.add('is-source'); // hide the small cover while the big one flies
  progress.configure(MOTION.springs.panel);
  progress.set(0);
  progress.to(1).then(() => {
    if (!closing) card.classList.remove('is-source');
  });
}

/** Returns a Promise that resolves once the dialog is fully closed. */
export function closeDetail() {
  if (!dialog?.open || closing) return Promise.resolve();
  closing = true;
  dialog.classList.remove('is-open');
  dialog.classList.add('is-closing');

  const finish = () => {
    dialog.close();
    dialog.classList.remove('is-closing');
    document.documentElement.classList.remove('has-modal');
    sourceCard?.classList.remove('is-source');
    coverEl.style.transform = '';
    const focusTarget = sourceCard?.isConnected ? sourceCard.querySelector('.card__hit') : lastFocus;
    focusTarget?.focus?.({ preventScroll: true });
    sourceCard = null;
    closing = false;
  };

  if (prefersReducedMotion()) {
    finish();
    return Promise.resolve();
  }
  // Measure again: the page or panel may have scrolled since opening.
  flip = measureFlip();
  sourceCard?.classList.add('is-source');
  progress.configure(MOTION.springs.panelClose);
  return progress.to(0).then(finish);
}
