/**
 * config.js — structure of the site + every animation knob in one place.
 *
 * Visual design tokens (colors, spacing, CSS easings/durations) live in
 * css/variables.css. Everything that JavaScript drives lives here.
 */

/* ------------------------------------------------------------------ *
 * Site structure
 * ------------------------------------------------------------------ */

/**
 * Primary sections, in navigation order.
 *   id     → used in the URL hash (#film/anime) and as the key in STRINGS.sections
 *   number → decorative index shown as the giant background numeral
 *   subs   → category ids (see CATEGORIES). A section with a single sub has no tab bar.
 */
export const SECTIONS = [
  { id: 'film', number: '01', subs: ['movie', 'tv', 'anime'] },
  { id: 'books', number: '02', subs: ['manga', 'literature'] },
  { id: 'music', number: '03', subs: ['music'] },
];

/**
 * Categories = one JSON file each.
 *   aspect → 'portrait' (2:3 posters / book covers) or 'square' (albums)
 */
export const CATEGORIES = {
  movie: { file: 'data/movie.json', aspect: 'portrait' },
  tv: { file: 'data/tv.json', aspect: 'portrait' },
  anime: { file: 'data/anime.json', aspect: 'portrait' },
  manga: { file: 'data/manga.json', aspect: 'portrait' },
  literature: { file: 'data/literature.json', aspect: 'portrait' },
  music: { file: 'data/music.json', aspect: 'square' },
};

export const SETTINGS_FILE = 'data/settings.json';

/** Defaults used when settings.json is missing or a key is absent. */
export const DEFAULT_SETTINGS = {
  titleMode: 'both', // 'english' | 'original' | 'both'
  deviceTilt: false, // tilt cards with the phone's gyroscope (touch devices only)
};

/** Default sort for every category. key: 'rating' | 'date' | 'title' */
export const DEFAULT_SORT = { key: 'date', dir: 'desc' };

/* ------------------------------------------------------------------ *
 * Motion — tweak these to change the "feel" of the site.
 *
 * Spring parameters:
 *   stiffness → higher = faster / snappier
 *   damping   → higher = less bounce (try 10 for wobbly, 30 for none)
 *   mass      → higher = heavier, slower to start and stop
 * Rule of thumb: damping ≈ 2·√(stiffness·mass) means "no overshoot".
 * ------------------------------------------------------------------ */

export const MOTION = {
  springs: {
    tiltFollow: { stiffness: 260, damping: 26, mass: 1 }, // card chasing the pointer
    tiltReturn: { stiffness: 170, damping: 11, mass: 1 }, // card settling back (visible wobble)
    cardEnter: { stiffness: 240, damping: 20, mass: 1 }, // cards popping into view
    panel: { stiffness: 260, damping: 26, mass: 1 }, // detail panel open (FLIP)
    panelClose: { stiffness: 340, damping: 34, mass: 1 }, // detail panel close
    indicator: { stiffness: 420, damping: 30, mass: 1 }, // sliding underline on tabs
  },

  /** Delay between consecutive items in a staggered entrance (ms). */
  stagger: 45,
  /** After this many items the stagger stops growing (keeps long lists snappy). */
  maxStaggerItems: 10,
  /** How far cards travel when entering (px). */
  enterDistance: 28,
  /** Old cards fade out this fast when switching section (ms). */
  exitDuration: 170,
  /** Number count-up duration (ms). */
  countDuration: 1100,
  /** Search typing debounce (ms). */
  searchDebounce: 120,
};

/** 3D tilt defaults (see js/tilt.js for what each one does). */
export const TILT = {
  maxTilt: 13, // degrees at the card edge
  perspective: 1000, // px — smaller = more dramatic 3D
  scale: 1.045, // hover lift
  glare: 0.32, // max glare opacity (0 disables)
  imageShift: 7, // px the artwork slides inside the frame (parallax)
  shadowShift: 14, // px the drop shadow slides
  touchFactor: 0.55, // tilt strength while pressing on touch screens
  pressScale: 0.975, // scale while pressing on touch screens
};
