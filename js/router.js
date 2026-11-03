/**
 * router.js — keeps the current section in the URL hash.
 *
 *   #film/movie   #film/tv   #film/anime
 *   #books/manga  #books/literature
 *   #music
 *
 * Anything unknown falls back to a valid route, so old/mistyped links still work.
 */

import { SECTIONS } from './config.js';

const lastSubOf = {}; // remembers the last tab used in each section

/** Turn a hash string into { section, sub } (always valid). */
export function parseHash(hash = location.hash) {
  const [sectionId, subId] = hash.replace(/^#\/?/, '').toLowerCase().split('/');
  const section = SECTIONS.find((s) => s.id === sectionId) || SECTIONS[0];
  let sub = section.subs.includes(subId) ? subId : null;
  if (!sub) sub = lastSubOf[section.id] || section.subs[0];
  return { section: section.id, sub };
}

/** Canonical hash for a route. Single-category sections use just "#music". */
export function hashFor(sectionId, subId) {
  const section = SECTIONS.find((s) => s.id === sectionId) || SECTIONS[0];
  const sub = subId || lastSubOf[section.id] || section.subs[0];
  return section.subs.length > 1 ? `#${section.id}/${sub}` : `#${section.id}`;
}

export function navigate(sectionId, subId) {
  const target = hashFor(sectionId, subId);
  if (location.hash !== target) location.hash = target;
}

/**
 * Call `callback(route)` whenever the hash changes.
 * Also rewrites invalid hashes to the canonical form (without adding history entries).
 */
export function onRouteChange(callback) {
  window.addEventListener('hashchange', () => callback(current()));
}

/** The current route; normalises the address bar as a side effect. */
export function current() {
  const route = parseHash();
  lastSubOf[route.section] = route.sub;
  const canonical = hashFor(route.section, route.sub);
  if (location.hash !== canonical) history.replaceState(null, '', canonical);
  return route;
}
