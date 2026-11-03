/**
 * strings.js — every piece of UI text on the site lives here.
 *
 * Rules:
 *   - No other file should contain user-visible English text.
 *   - Placeholders look like {name}; fill them with t(STRINGS.x.y, { name: 'value' }).
 *   - To add another language later, copy this object, translate it,
 *     and switch which object is exported.
 *
 * Note: index.html also contains a fallback <title>/<meta description>/<noscript>
 * (needed before JavaScript runs). Keep those in sync with `site` below.
 */

export const STRINGS = {
  site: {
    title: 'MEDIA LOG — Personal Archive',
    description: 'A personal log of films, series, books and music.',
    brand: 'MEDIA LOG',
    brandTag: 'PERSONAL ARCHIVE',
    tagline: 'A RECORD OF THINGS SEEN, READ AND HEARD',
    scroll: 'SCROLL',
    skipToContent: 'Skip to content',
    homeLabel: 'Media Log — home',
  },

  nav: {
    label: 'Primary sections',
    subLabel: 'Subsections',
  },

  // Primary sections (keys must match SECTIONS in config.js)
  sections: {
    film: 'FILM & SERIES',
    books: 'BOOKS',
    music: 'MUSIC',
  },
  sectionCode: 'SECTION {n}',

  // Categories / sub-tabs (keys must match CATEGORIES in config.js)
  categories: {
    movie: 'MOVIES',
    tv: 'TV SERIES',
    anime: 'ANIME',
    manga: 'MANGA',
    literature: 'FICTION',
    music: 'ALBUMS',
  },

  // Short decorative codes printed on placeholder covers
  categoryCodes: {
    movie: 'MOV',
    tv: 'TV',
    anime: 'ANI',
    manga: 'MNG',
    literature: 'FIC',
    music: 'MUS',
  },

  stats: {
    label: 'Statistics',
    total: 'ENTRIES',
    average: 'AVG RATING',
    averageUnit: '/ 5',
    latest: 'LATEST',
    none: '—',
  },

  toolbar: {
    label: 'Sort and filter',
    searchPlaceholder: 'SEARCH TITLE / CREATOR / TAG',
    searchLabel: 'Search this category',
    clearSearch: 'Clear search',
    sortLabel: 'SORT',
    sort: {
      rating: 'RATING',
      date: 'DATE ADDED',
      title: 'TITLE',
    },
    toggleDir: 'Toggle sort direction',
    dirAsc: 'ASC',
    dirDesc: 'DESC',
    tagsLabel: 'TAGS',
    tagFilterLabel: 'Filter by tags',
    clearTags: 'CLEAR',
    results: '{n} / {total}',
    resultsAria: 'Showing {n} of {total} entries',
  },

  card: {
    file: 'FILE / {n}',
    open: 'Open details: {title}',
    noCover: 'NO COVER',
  },

  rating: {
    label: 'RATING',
    aria: 'Rated {n} out of 5',
  },

  detail: {
    dialogLabel: 'Entry details',
    close: 'CLOSE',
    closeAria: 'Close details',
    file: 'FILE / {n}',
    originalTitle: 'ORIGINAL TITLE',
    alsoKnownAs: 'ALSO KNOWN AS',
    year: 'YEAR',
    rating: 'RATING',
    date: 'LOGGED',
    tags: 'TAGS',
    review: 'REVIEW',
    noReview: 'NO REVIEW RECORDED.',
    // Creator label depends on the category
    creator: {
      movie: 'DIRECTOR',
      tv: 'CREATOR',
      anime: 'DIRECTOR',
      manga: 'AUTHOR',
      literature: 'AUTHOR',
      music: 'ARTIST',
    },
  },

  empty: {
    title: 'NO RESULTS',
    hint: 'Nothing matches. Try another keyword or clear the tag filter.',
    categoryTitle: 'NO ENTRIES YET',
    categoryHint: 'Add one with: python scripts/add.py',
    reset: 'RESET FILTERS',
  },

  error: {
    title: 'DATA LOAD FAILED',
    hint: 'Could not read {file}. If you opened index.html directly from disk, run "python -m http.server" in the project folder and open http://localhost:8000 instead.',
    retry: 'RETRY',
  },

  loading: 'LOADING',
};

/** Fill {placeholders} in a template string. */
export function t(template, vars = {}) {
  return String(template).replace(/\{(\w+)\}/g, (_, key) => (key in vars ? vars[key] : ''));
}
