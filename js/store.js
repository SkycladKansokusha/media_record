/**
 * store.js — loading JSON, cleaning entries, search / filter / sort / stats.
 *
 * Nothing in here touches the DOM, so it's the easiest file to read first.
 * Derived fields added to each entry start with "_" so they can't clash with
 * fields you write in the JSON.
 */

import { CATEGORIES, DEFAULT_SETTINGS, SETTINGS_FILE } from './config.js';

const cache = new Map(); // category → Promise<entries[]>

/* ------------------------------------------------------------------ *
 * Loading
 * ------------------------------------------------------------------ */

async function fetchJSON(url) {
  // 'no-cache' = always ask the server whether the file changed,
  // so editing a JSON file + refreshing shows the change immediately.
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

export async function loadSettings() {
  try {
    const raw = await fetchJSON(SETTINGS_FILE);
    const settings = { ...DEFAULT_SETTINGS, ...raw };
    if (!['english', 'original', 'both'].includes(settings.titleMode)) {
      console.warn(`settings.json: unknown titleMode "${settings.titleMode}", using "both"`);
      settings.titleMode = 'both';
    }
    return settings;
  } catch {
    return { ...DEFAULT_SETTINGS }; // settings are optional
  }
}

/** Load (once) and normalise one category. Rejects with an Error on failure. */
export function loadCategory(category) {
  if (!cache.has(category)) {
    const promise = fetchJSON(CATEGORIES[category].file)
      .then((raw) => {
        if (!Array.isArray(raw)) throw new Error(`${CATEGORIES[category].file}: expected an array`);
        return prepareEntries(raw, category);
      })
      .catch((err) => {
        cache.delete(category); // allow retry
        throw err;
      });
    cache.set(category, promise);
  }
  return cache.get(category);
}

/* ------------------------------------------------------------------ *
 * Normalising
 * ------------------------------------------------------------------ */

/** Lowercase + NFKC so "ＡＢＣ", "abc" and "Abc" all match, and half/full-width CJK too. */
export function normalizeText(value) {
  return String(value ?? '').normalize('NFKC').toLowerCase().trim();
}

const KANA = /[぀-ヿ]/;
const HANGUL = /[ᄀ-ᇿ㄰-㆏가-힯]/;
const HAN = /[㐀-䶿一-鿿豈-﫿]/;

/**
 * Best-effort language guess from the writing system (for `lang` attributes
 * when the JSON doesn't say). Kana → ja, Hangul → ko, Han only → zh, else ''.
 */
export function guessLang(text) {
  if (!text) return '';
  if (KANA.test(text)) return 'ja';
  if (HANGUL.test(text)) return 'ko';
  if (HAN.test(text)) return 'zh';
  return '';
}

const asString = (v) => (typeof v === 'string' ? v.trim() : '');
const asStringList = (v) => (Array.isArray(v) ? v.filter((x) => typeof x === 'string' && x.trim()).map((x) => x.trim()) : []);

/** Round to the nearest 0.5 and clamp to 0–5, so bad data can't break the diamonds. */
function cleanRating(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return 0;
  return Math.min(5, Math.max(0, Math.round(n * 2) / 2));
}

function prepareEntries(raw, category) {
  const list = [];
  raw.forEach((item, index) => {
    if (!item || typeof item !== 'object') return;
    const originalTitle = asString(item.originalTitle);
    // Fallback rule: no title → use the original title.
    const title = asString(item.title) || originalTitle;
    if (!title) {
      console.warn(`${category}.json #${index + 1}: entry has no title, skipped`);
      return;
    }
    const entry = {
      ...item,
      id: asString(item.id) || `${category}-auto-${index}`,
      title,
      originalTitle,
      originalLanguage: asString(item.originalLanguage) || guessLang(originalTitle),
      altTitles: asStringList(item.altTitles),
      creator: asString(item.creator),
      creatorOriginal: asString(item.creatorOriginal),
      review: typeof item.review === 'string' ? item.review : '',
      tags: asStringList(item.tags),
      cover: asString(item.cover),
      year: Number.isFinite(Number(item.year)) && item.year !== '' ? Number(item.year) : null,
      rating: cleanRating(item.rating),
      date: asString(item.date),
      _category: category,
    };
    entry._time = Date.parse(`${entry.date}T00:00:00Z`) || 0;
    entry._sortTitle = sortableTitle(entry.title);
    entry._search = normalizeText(
      [entry.title, entry.originalTitle, ...entry.altTitles, entry.creator, entry.creatorOriginal, ...entry.tags].join('\u0001'),
    );
    list.push(entry);
  });

  // FILE / 001 numbers = order in which entries were logged (oldest = 001).
  [...list]
    .sort((a, b) => a._time - b._time || a.id.localeCompare(b.id))
    .forEach((entry, i) => (entry._fileNo = String(i + 1).padStart(3, '0')));
  return list;
}

/* ------------------------------------------------------------------ *
 * Title display
 * ------------------------------------------------------------------ */

/** Same text ignoring case and surrounding spaces? */
export function sameTitle(a, b) {
  return normalizeText(a) === normalizeText(b);
}

/**
 * Decide what to show as the main title and the smaller subtitle.
 * Returns { primary: {text, lang}, secondary: {text, lang} | null }.
 *
 *   'both'     → English title, original underneath (if different)
 *   'english'  → English title only
 *   'original' → original title first, English underneath (if different)
 */
export function displayTitles(entry, mode = 'both') {
  const english = { text: entry.title, lang: entry.title === entry.originalTitle ? entry.originalLanguage || 'en' : 'en' };
  const hasOriginal = entry.originalTitle && !sameTitle(entry.originalTitle, entry.title);
  const original = hasOriginal ? { text: entry.originalTitle, lang: entry.originalLanguage || guessLang(entry.originalTitle) } : null;

  if (mode === 'english') return { primary: english, secondary: null };
  if (mode === 'original' && original) return { primary: original, secondary: english };
  return { primary: english, secondary: original };
}

/** Same idea for the creator line in the detail panel. */
export function displayCreator(entry) {
  const hasOriginal = entry.creatorOriginal && !sameTitle(entry.creatorOriginal, entry.creator);
  return {
    primary: entry.creator || entry.creatorOriginal,
    secondary: hasOriginal && entry.creator ? entry.creatorOriginal : '',
    secondaryLang: guessLang(entry.creatorOriginal) || entry.originalLanguage,
  };
}

/* ------------------------------------------------------------------ *
 * Search / filter / sort
 * ------------------------------------------------------------------ */

/** "The Remains of the Day" → "Remains of the Day" for sorting. */
export function sortableTitle(title) {
  return title.replace(/^(the|a|an)\s+/i, '');
}

const collator = new Intl.Collator('en', { sensitivity: 'base', numeric: true });

/**
 * @param entries all entries of a category
 * @param query   free text; every whitespace-separated word must match
 * @param tags    Set of tags; entries must have ALL selected tags
 */
export function filterEntries(entries, { query = '', tags = new Set() } = {}) {
  const words = normalizeText(query).split(/\s+/).filter(Boolean);
  return entries.filter((e) => {
    if (words.length && !words.every((w) => e._search.includes(w))) return false;
    for (const tag of tags) if (!e.tags.includes(tag)) return false;
    return true;
  });
}

export function sortEntries(entries, key = 'date', dir = 'desc') {
  const sign = dir === 'asc' ? 1 : -1;
  const byTitle = (a, b) => collator.compare(a._sortTitle, b._sortTitle);
  const comparators = {
    rating: (a, b) => sign * (a.rating - b.rating) || b._time - a._time || byTitle(a, b),
    date: (a, b) => sign * (a._time - b._time) || byTitle(a, b),
    title: (a, b) => sign * byTitle(a, b) || b._time - a._time,
  };
  return [...entries].sort(comparators[key] || comparators.date);
}

/** All tags with how often they appear, most common first. */
export function collectTags(entries) {
  const counts = new Map();
  entries.forEach((e) => e.tags.forEach((t) => counts.set(t, (counts.get(t) || 0) + 1)));
  return [...counts].sort((a, b) => b[1] - a[1] || collator.compare(a[0], b[0])).map(([tag, count]) => ({ tag, count }));
}

export function computeStats(entries) {
  const rated = entries.filter((e) => e.rating > 0);
  const average = rated.length ? rated.reduce((sum, e) => sum + e.rating, 0) / rated.length : 0;
  const latest = entries.reduce((best, e) => (!best || e._time > best._time ? e : best), null);
  return { total: entries.length, average, latest };
}
