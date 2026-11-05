#!/usr/bin/env python3
"""
add.py — interactively add an entry: search online → pick → edit → download cover → save.

Usage:
    python scripts/add.py              # guided mode
    python scripts/add.py --manual     # skip the online search, type everything yourself
    python scripts/add.py -c anime     # preselect a category

Data sources:
    movie, tv        TMDB          (needs env var TMDB_API_KEY — v3 key or v4 read token)
    anime, manga     AniList       (no key)
    literature       Open Library, falling back to Google Books (no key)
    music            iTunes Search (no key)

Requires `requests`. `Pillow` is optional: with it covers are converted to
JPEG and resized; without it the downloaded file is saved as-is.
"""

from __future__ import annotations

import argparse
import datetime as dt
import io
import os
import re
import shutil
import sys
from pathlib import Path

from common import (
    CATEGORIES, DATE_RE, LANG_RE, ROOT, Colors, cover_dir, guess_lang, has_cjk,
    is_valid_rating, load_entries, save_entries, setup_console,
)

try:
    import requests
except ImportError:  # pragma: no cover
    print("This script needs the 'requests' package:  pip install -r requirements.txt")
    sys.exit(1)

try:
    from PIL import Image  # optional
except ImportError:
    Image = None

TIMEOUT = 15
MAX_RESULTS = 8
COVER_MAX_SIZE = 1200  # px, longest side (only when Pillow is installed)
# How many tags to prefill from a data source (tags you type are never limited or filtered).
MAX_TAGS = 3
# Longer candidates are noise (Open Library subjects can be whole sentences).
TAG_MAX_LENGTH = 40
# Canonical spellings of the genres every category may use; whitelists only contain canonical names.
GENRES_COMMON = {
    "Action", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Family", "Fantasy", "History", "Horror",
    "Music", "Musical", "Mystery", "Romance", "Sci-Fi", "Sport",
    "Thriller", "War", "Western",
}
# Extra genres that are common for anime only.
GENRES_ANIME_EXTRA = {
    "Isekai", "Mecha", "Iyashikei", "Slice of Life", "School", "Supernatural",
    "Psychological", "Sports", "Magic", "Magical Girl", "Military",
    "Martial Arts", "Space", "Super Power", "Idol",
}
# Target-audience tags; manga keeps one of them in the last position (see filter_tags).
DEMOGRAPHICS = {"Shonen", "Seinen", "Shojo", "Josei", "Kodomomuke"}
# Whitelist per category; None = no whitelist (only the generic "Music" is dropped).
ALLOWED_TAGS = {
    "movie": GENRES_COMMON,
    "tv": GENRES_COMMON,
    "literature": GENRES_COMMON,
    "anime": GENRES_COMMON | GENRES_ANIME_EXTRA,
    "manga": GENRES_COMMON | DEMOGRAPHICS,
    "music": None,
}
# Always dropped, before and after alias conversion: any candidate containing one of these (lowercase).
BLOCKED_TAGS = {
    "ecchi", "hentai", "harem", "reverse harem", "erotica", "nudity",
    "sexual content", "lolicon", "shotacon", "borderline porn", "pornography",
}
# Lowercase candidate → canonical name(s), expanded in place. "sports" stays "Sports" for anime (see resolve_tag).
TAG_ALIASES = {
    "science fiction": ["Sci-Fi"], "sci fi": ["Sci-Fi"], "scifi": ["Sci-Fi"], "sf": ["Sci-Fi"],
    "sci-fi & fantasy": ["Sci-Fi", "Fantasy"],
    "action & adventure": ["Action", "Adventure"],
    "war & politics": ["War"],
    "suspense": ["Thriller"],
    "detective": ["Mystery"], "detective and mystery": ["Mystery"], "mystery and detective": ["Mystery"],
    "historical": ["History"], "historical fiction": ["History"],
    "sports": ["Sport"],
    "shounen": ["Shonen"], "shoujo": ["Shojo"],
    "kids": ["Kodomomuke"], "children": ["Kodomomuke"],
    "mahou shoujo": ["Magical Girl"],
}
# Book subjects: "Fantasy fiction" is matched as "Fantasy" (literature only).
BOOK_TAG_SUFFIX_RE = re.compile(r"\s+(?:fiction|stories|novels|literature)$", re.I)
# How many dropped candidates the "(filtered out: …)" hint lists.
MAX_FILTERED_SHOWN = 6
HEADERS = {"User-Agent": "my-media-log/1.0 (personal archive script)"}

C = Colors


class Cancel(Exception):
    """Raised to abort the whole flow cleanly."""


# ====================================================================
# Small input helpers
# ====================================================================

def ask(prompt: str, default: str = "", allow_clear: bool = True) -> str:
    """
    Ask for text. Enter keeps the default. Typing a single "-" clears the value.
    """
    hint = f" [{C.cyan(default)}]" if default else ""
    raw = input(f"{prompt}{hint}: ").strip()
    if raw == "-" and allow_clear:
        return ""
    return raw or default


def ask_choice(prompt: str, options: list[str], default: int | None = None) -> int:
    """Numbered menu, returns the 0-based index."""
    for i, opt in enumerate(options, 1):
        print(f"  {C.cyan(str(i)):>4}  {opt}")
    while True:
        hint = f" [{default + 1}]" if default is not None else ""
        raw = input(f"{prompt}{hint}: ").strip()
        if not raw and default is not None:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw) - 1
        print(C.yellow(f"  Please enter a number between 1 and {len(options)}."))


def ask_yes(prompt: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    raw = input(f"{prompt} ({hint}): ").strip().lower()
    return default if not raw else raw in ("y", "yes")


def ask_rating() -> float | int:
    while True:
        raw = input("Rating 1–5 (half steps allowed, e.g. 3.5): ").strip()
        try:
            value = float(raw)
        except ValueError:
            print(C.yellow("  Not a number."))
            continue
        if is_valid_rating(value):
            return int(value) if value.is_integer() else value
        print(C.yellow("  Must be between 1 and 5 in steps of 0.5 (1, 1.5, 2 … 5)."))


def ask_year(default) -> int | None:
    while True:
        raw = ask("Year", str(default or ""))
        if not raw:
            print(C.yellow("  Year is required."))
            continue
        if raw.isdigit() and 1000 <= int(raw) <= 2100:
            return int(raw)
        print(C.yellow("  Please enter a 4-digit year."))


def ask_date() -> str:
    today = dt.date.today().isoformat()
    while True:
        raw = ask("Date logged (YYYY-MM-DD)", today, allow_clear=False)
        if DATE_RE.match(raw):
            try:
                dt.date.fromisoformat(raw)
                return raw
            except ValueError:
                pass
        print(C.yellow("  Use the format YYYY-MM-DD, e.g. 2026-10-20."))


def ask_lang(default: str) -> str:
    while True:
        raw = ask('Original language code (ja, zh, zh-Hant, ko, fr …, "-" to clear)', default)
        if not raw or LANG_RE.match(raw):
            return raw
        print(C.yellow('  Not a valid code. Examples: "ja", "zh", "zh-Hant", "ko", "en", "pt-BR".'))


def ask_list(prompt: str, default: list[str], sep: str) -> list[str]:
    shown = f" {sep} ".join(default)
    raw = ask(f'{prompt} (separate with "{sep}")', shown)
    return [x.strip() for x in raw.split(sep) if x.strip()]


def ask_tags(auto_tags: list[str]) -> list[str]:
    """Prefilled tags can be kept, replaced or cleared; with none, ask until typed or declined."""
    if auto_tags:
        return ask_list("Tags (auto-filled, Enter to keep)", auto_tags, ",")
    print(C.yellow("  No common tags found online — please enter some (comma-separated)."))
    while True:
        tags = ask_list("Tags", [], ",")
        if tags or ask_yes("  Save without tags?", False):
            return tags


def ask_review() -> str:
    print('Review — multiple lines allowed. Finish with a line containing only "."')
    print(C.dim('  (Leave the first line empty and press Enter to skip.)'))
    lines: list[str] = []
    while True:
        line = input("  > " if not lines else "  . ")
        if line.strip() == "." or (not lines and line == ""):
            break
        lines.append(line.rstrip())
    return "\n".join(lines).strip()


# ====================================================================
# HTTP helpers
# ====================================================================

def http_get(url: str, **kwargs):
    try:
        resp = requests.get(url, headers={**HEADERS, **kwargs.pop("headers", {})}, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as e:
        raise ConnectionError(f"Network error: {e.__class__.__name__}. Check your connection and try again.") from e
    if resp.status_code == 401:
        raise ConnectionError("The server rejected the API key (HTTP 401). Check TMDB_API_KEY.")
    if resp.status_code == 429:
        raise ConnectionError("Too many requests (HTTP 429). Wait a minute and try again.")
    if not resp.ok:
        raise ConnectionError(f"Server returned HTTP {resp.status_code}.")
    return resp


def http_post_json(url: str, payload: dict):
    try:
        resp = requests.post(url, json=payload, headers={**HEADERS, "Accept": "application/json"}, timeout=TIMEOUT)
    except requests.RequestException as e:
        raise ConnectionError(f"Network error: {e.__class__.__name__}. Check your connection and try again.") from e
    if resp.status_code == 429:
        raise ConnectionError("AniList rate limit reached. Wait a minute and try again.")
    if not resp.ok:
        raise ConnectionError(f"Server returned HTTP {resp.status_code}.")
    return resp


# ====================================================================
# Providers
#   search(query) -> list of result dicts:
#     { title, originalTitle, originalLanguage, altTitles, creator,
#       creatorOriginal, year, coverUrl, source: {provider, id} }
#   details(result) -> result with extra fields filled (optional)
# ====================================================================

def year_of(text) -> int | None:
    m = re.match(r"(\d{4})", str(text or ""))
    return int(m.group(1)) if m else None


def is_blocked_tag(tag: str) -> bool:
    key = tag.casefold()
    return any(word in key for word in BLOCKED_TAGS)


def resolve_tag(tag: str, category: str) -> list[str]:
    """Candidate → the name(s) to look up in the whitelist (aliases and book suffixes applied)."""
    key = tag.casefold()
    if key == "sports" and category == "anime":
        return [tag]
    if key in TAG_ALIASES:
        return TAG_ALIASES[key]
    if category == "literature":
        stripped = BOOK_TAG_SUFFIX_RE.sub("", tag)
        return TAG_ALIASES.get(stripped.casefold(), [stripped])
    return [tag]


def filter_tags(raw_tags, category: str, limit: int = MAX_TAGS) -> tuple[list[str], list[str]]:
    """Returns (kept tags, candidates dropped as blocked or not whitelisted). No network access."""
    allowed = ALLOWED_TAGS[category]
    canonical = {name.casefold(): name for name in allowed or ()}
    kept, dropped = [], []
    for raw in raw_tags or []:
        tag = raw.strip() if isinstance(raw, str) else ""
        if not tag or len(tag) > TAG_MAX_LENGTH or ":" in tag or ";" in tag:
            continue
        if is_blocked_tag(tag):
            dropped.append(tag)
        elif allowed is None:
            (dropped if tag.casefold() == "music" else kept).append(tag)
        else:
            names = [canonical[n.casefold()] for n in resolve_tag(tag, category)
                     if n.casefold() in canonical and not is_blocked_tag(n)]
            kept.extend(names)
            if not names:
                dropped.append(tag)
    unique = list({t.casefold(): t for t in kept}.values())
    if category == "manga":
        demographic = next((t for t in unique if t in DEMOGRAPHICS), None)
        if demographic:
            genres = [t for t in unique if t not in DEMOGRAPHICS]
            return genres[:limit - 1] + [demographic], list(dict.fromkeys(dropped))
    return unique[:limit], list(dict.fromkeys(dropped))


def clean_tags(raw_tags, category: str, limit: int = MAX_TAGS) -> list[str]:
    return filter_tags(raw_tags, category, limit)[0]


def tag_fields(raw_tags, category: str) -> dict:
    """The tag keys of a search result; _filteredTags is only shown as a hint before the Tags prompt."""
    tags, filtered = filter_tags(raw_tags, category)
    return {"tags": tags, "_filteredTags": filtered}


# ---------------------------- TMDB (movie / tv) ----------------------------

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p/w780"


def tmdb_request(path: str, **params):
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        raise ConnectionError(
            "TMDB_API_KEY is not set. Get a free key at https://www.themoviedb.org/settings/api\n"
            "  then run:  export TMDB_API_KEY=your_key   (Windows: set TMDB_API_KEY=your_key)\n"
            "  Or choose manual mode."
        )
    headers = {}
    if key.startswith("eyJ"):  # v4 "API Read Access Token"
        headers["Authorization"] = f"Bearer {key}"
    else:  # v3 API key
        params["api_key"] = key
    return http_get(f"{TMDB_API}{path}", params=params, headers=headers).json()


def tmdb_search(kind: str, query: str) -> list[dict]:
    data = tmdb_request(f"/search/{kind}", query=query, language="en-US", include_adult="false")
    results = []
    for r in data.get("results", [])[:MAX_RESULTS]:
        title = r.get("title") or r.get("name") or ""
        original = r.get("original_title") or r.get("original_name") or ""
        results.append({
            "title": title,
            "originalTitle": original,
            "originalLanguage": r.get("original_language") or "",
            "altTitles": [],
            "creator": "",
            "creatorOriginal": "",
            "year": year_of(r.get("release_date") or r.get("first_air_date")),
            "coverUrl": f"{TMDB_IMG}{r['poster_path']}" if r.get("poster_path") else "",
            "source": {"provider": "tmdb", "id": str(r.get("id"))},
            "tags": [],
            "_kind": kind,
        })
    return results


def tmdb_details(item: dict) -> dict:
    """Fetch director / creator, genres as tags, and a Chinese title as a suggested altTitle."""
    kind, tid = item["_kind"], item["source"]["id"]
    try:
        info = tmdb_request(f"/{kind}/{tid}", language="en-US")
        item.update(tag_fields([g.get("name") for g in info.get("genres", [])], kind))
        if kind == "movie":
            credits = tmdb_request(f"/movie/{tid}/credits", language="en-US")
            directors = [c["name"] for c in credits.get("crew", []) if c.get("job") == "Director"]
            item["creator"] = ", ".join(directors[:2])
        else:
            item["creator"] = ", ".join(c["name"] for c in info.get("created_by", [])[:2])
        zh = tmdb_request(f"/{kind}/{tid}", language="zh-CN")
        zh_title = zh.get("title") or zh.get("name") or ""
        if zh_title and zh_title not in (item["title"], item["originalTitle"]):
            item["altTitles"] = [zh_title]
    except ConnectionError as e:
        print(C.yellow(f"  (Could not load extra details: {e})"))
    return item


# ---------------------------- AniList (anime / manga) ----------------------------

ANILIST_API = "https://graphql.anilist.co"
ANILIST_QUERY = """
query ($search: String, $type: MediaType, $perPage: Int) {
  Page(perPage: $perPage) {
    media(search: $search, type: $type, sort: SEARCH_MATCH) {
      id
      format
      countryOfOrigin
      title { romaji english native }
      startDate { year }
      coverImage { extraLarge large }
      genres
      tags { name rank isMediaSpoiler isGeneralSpoiler }
      studios(isMain: true) { nodes { name } }
      staff(perPage: 12, sort: [RELEVANCE]) {
        edges { role node { name { full native } } }
      }
    }
  }
}
"""
COUNTRY_TO_LANG = {"JP": "ja", "KR": "ko", "CN": "zh", "TW": "zh-Hant", "HK": "zh-Hant"}


def pick_staff(edges: list, kind: str):
    """Director for anime; author (Story/Art/Original Creator) for manga.
    kind "NOVEL": the writer only — never the illustrator, so no fallback to the first staff member."""
    if kind == "NOVEL":
        wanted = ["Story", "Original Creator", "Original Story", "Story & Art"]
    else:
        wanted = ["Director"] if kind == "ANIME" else ["Story & Art", "Story", "Original Creator", "Original Story", "Art"]
    for role in wanted:
        for e in edges:
            if (e.get("role") or "").split(" (")[0] == role:
                return e["node"]["name"]
    if kind == "NOVEL":
        return None
    return edges[0]["node"]["name"] if edges else None


def anilist_tags(media: dict) -> list[str]:
    """Tag candidates: genres first, then non-spoiler tags from the highest rank down."""
    tags = [t for t in media.get("tags") or [] if not t.get("isMediaSpoiler") and not t.get("isGeneralSpoiler")]
    tags.sort(key=lambda t: t.get("rank") or 0, reverse=True)
    return [*(media.get("genres") or []), *(t.get("name") for t in tags)]


def anilist_search(kind: str, query: str, fmt: str | None = None) -> list[dict]:
    """fmt: optional MediaFormat filter (e.g. "NOVEL"); without it the query is unchanged."""
    gql = ANILIST_QUERY
    variables = {"search": query, "type": kind, "perPage": MAX_RESULTS}
    if fmt:
        gql = gql.replace("$perPage: Int)", "$perPage: Int, $format: MediaFormat)", 1)
        gql = gql.replace("type: $type,", "type: $type, format: $format,", 1)
        variables["format"] = fmt
    payload = {"query": gql, "variables": variables}
    data = http_post_json(ANILIST_API, payload).json()
    if data.get("errors"):
        raise ConnectionError(f"AniList error: {data['errors'][0].get('message')}")
    results = []
    for m in data["data"]["Page"]["media"]:
        t = m.get("title") or {}
        name = pick_staff((m.get("staff") or {}).get("edges") or [], "NOVEL" if fmt == "NOVEL" else kind) or {}
        studios = [s["name"] for s in (m.get("studios") or {}).get("nodes", [])]
        creator = name.get("full") or ""
        if kind == "ANIME" and not creator and studios:
            creator = studios[0]
        results.append({
            # English title first; romaji when no official English title exists
            "title": t.get("english") or t.get("romaji") or "",
            "originalTitle": t.get("native") or "",
            "originalLanguage": COUNTRY_TO_LANG.get(m.get("countryOfOrigin"), "") or guess_lang(t.get("native") or ""),
            "altTitles": [t["romaji"]] if t.get("english") and t.get("romaji") and t["romaji"] != t["english"] else [],
            "creator": creator,
            "creatorOriginal": name.get("native") or "",
            "year": (m.get("startDate") or {}).get("year"),
            "coverUrl": (m.get("coverImage") or {}).get("extraLarge") or (m.get("coverImage") or {}).get("large") or "",
            "source": {"provider": "anilist", "id": str(m["id"])},
            **tag_fields(anilist_tags(m), "literature" if fmt == "NOVEL" else kind.lower()),
            "_extra": m.get("format") or "",
        })
    return results


# ---------------------------- Open Library (literature) ----------------------------

ISO639_2_TO_1 = {
    "eng": "en", "jpn": "ja", "chi": "zh", "zho": "zh", "kor": "ko", "fre": "fr", "fra": "fr",
    "ger": "de", "deu": "de", "spa": "es", "ita": "it", "rus": "ru", "por": "pt",
}


def google_books_search(query: str) -> list[dict]:
    """Fallback for books Open Library doesn't know (common for Chinese / Japanese titles)."""
    params = {"q": query, "maxResults": MAX_RESULTS, "printType": "books"}
    data = http_get("https://www.googleapis.com/books/v1/volumes", params=params).json()
    results = []
    for item in data.get("items", [])[:MAX_RESULTS]:
        info = item.get("volumeInfo", {})
        title = info.get("title") or ""
        authors = info.get("authors") or []
        cjk = has_cjk(title)
        thumb = (info.get("imageLinks") or {}).get("thumbnail", "")
        results.append({
            "title": "" if cjk else title,
            "originalTitle": title if cjk else "",
            "originalLanguage": (info.get("language") or guess_lang(title)) if cjk else "",
            "altTitles": [],
            "creator": "" if authors and has_cjk(authors[0]) else ", ".join(authors[:2]),
            "creatorOriginal": authors[0] if authors and has_cjk(authors[0]) else "",
            "year": year_of(info.get("publishedDate")),
            # larger image than the default thumbnail, over https
            "coverUrl": thumb.replace("http://", "https://").replace("&edge=curl", "").replace("zoom=1", "zoom=3") if thumb else "",
            "source": {"provider": "googlebooks", "id": item.get("id", "")},
            **tag_fields([part for c in info.get("categories") or [] for part in c.split("/")], "literature"),
        })
    return results


def books_search(query: str) -> list[dict]:
    """Open Library first; fill up with Google Books when it finds little."""
    results: list[dict] = []
    try:
        results = openlibrary_search(query)
    except ConnectionError as e:
        print(C.dim(f"  Open Library unavailable ({e}); trying Google Books …"))
    if len(results) < 3:
        try:
            results += google_books_search(query)
        except ConnectionError as e:
            if not results:
                raise e
    return results[:MAX_RESULTS]


def openlibrary_search(query: str) -> list[dict]:
    params = {
        "q": query, "limit": MAX_RESULTS,
        "fields": "key,title,author_name,first_publish_year,cover_i,language,subject",
    }
    data = http_get("https://openlibrary.org/search.json", params=params).json()
    results = []
    for d in data.get("docs", [])[:MAX_RESULTS]:
        title = d.get("title") or ""
        author = (d.get("author_name") or [""])[0]
        langs = d.get("language") or []
        lang = ISO639_2_TO_1.get(langs[0], "") if len(langs) == 1 else ""
        original = ""
        if has_cjk(title):  # a CJK title is the original; English one must be typed in
            original, lang = title, lang or guess_lang(title)
        results.append({
            "title": "" if original else title,
            "originalTitle": original,
            "originalLanguage": lang,
            "altTitles": [],
            "creator": "" if has_cjk(author) else ", ".join((d.get("author_name") or [])[:2]),
            "creatorOriginal": author if has_cjk(author) else "",
            "year": d.get("first_publish_year"),
            "coverUrl": f"https://covers.openlibrary.org/b/id/{d['cover_i']}-L.jpg" if d.get("cover_i") else "",
            "source": {"provider": "openlibrary", "id": (d.get("key") or "").split("/")[-1]},
            **tag_fields(d.get("subject"), "literature"),
        })
    return results


# ---------------------------- iTunes (music) ----------------------------

# A CJK query searches the matching regional store (the US store barely knows CJK titles).
ITUNES_COUNTRY = {"ja": "JP", "ko": "KR", "zh": "TW"}


def itunes_search(query: str) -> list[dict]:
    params = {"term": query, "entity": "album", "limit": MAX_RESULTS, "media": "music",
              "country": ITUNES_COUNTRY.get(guess_lang(query), "US")}
    data = http_get("https://itunes.apple.com/search", params=params).json()
    if not data.get("results") and params["country"] != "US":  # not in that regional store
        params["country"] = "US"
        data = http_get("https://itunes.apple.com/search", params=params).json()
    results = []
    for r in data.get("results", [])[:MAX_RESULTS]:
        name = r.get("collectionName") or ""
        name = re.sub(r"\s*-\s*(Single|EP)$", "", name)
        artist = r.get("artistName") or ""
        cjk = has_cjk(name)
        art = r.get("artworkUrl100") or ""
        results.append({
            "title": "" if cjk else name,
            "originalTitle": name if cjk else "",
            "originalLanguage": guess_lang(name) if cjk else "",
            "altTitles": [],
            "creator": "" if has_cjk(artist) else artist,
            "creatorOriginal": artist if has_cjk(artist) else "",
            "year": year_of(r.get("releaseDate")),
            "coverUrl": art.replace("100x100bb", "1000x1000bb") if art else "",
            "source": {"provider": "itunes", "id": str(r.get("collectionId", ""))},
            **tag_fields([r.get("primaryGenreName")], "music"),
        })
    return results


def search(category: str, query: str) -> list[dict]:
    if category in ("movie", "tv"):
        return tmdb_search(category, query)
    if category == "anime":
        return anilist_search("ANIME", query)
    if category == "manga":
        return anilist_search("MANGA", query)
    if category == "literature":
        return literature_search(query)
    return itunes_search(query)


def literature_search(query: str) -> list[dict]:
    """Light novels from AniList first; fill up with Open Library / Google Books when it finds little."""
    results: list[dict] = []
    try:
        results = anilist_search("MANGA", query, fmt="NOVEL")
    except ConnectionError as e:
        print(C.dim(f"  AniList unavailable ({e}); trying book sources …"))
    if len(results) < 3:
        try:
            books = books_search(query)
        except ConnectionError as e:
            if not results:
                raise e
            books = []
        seen = {norm(r["title"] or r["originalTitle"]) for r in results}
        for b in books:
            key = norm(b["title"] or b["originalTitle"])
            if key not in seen:
                seen.add(key)
                results.append(b)
    return results[:MAX_RESULTS]


def details(category: str, item: dict) -> dict:
    if category in ("movie", "tv"):
        return tmdb_details(item)
    return item


# ====================================================================
# Covers
# ====================================================================

def entry_cover_dir(entry_id: str) -> Path:
    """covers/<category>/ for an id like "anime-0014" (ids are always <category>-NNNN)."""
    return cover_dir(entry_id.rsplit("-", 1)[0])


def save_cover_bytes(data: bytes, entry_id: str, content_type: str = "") -> str:
    """Save image bytes as covers/<category>/<id>.jpg (Pillow) or with its original extension (no Pillow)."""
    folder = entry_cover_dir(entry_id)
    if Image is not None:
        try:
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
            img.thumbnail((COVER_MAX_SIZE, COVER_MAX_SIZE))
            path = folder / f"{entry_id}.jpg"
            img.save(path, "JPEG", quality=88, optimize=True, progressive=True)
            return path.relative_to(ROOT).as_posix()
        except Exception as e:  # corrupt / unsupported image
            print(C.yellow(f"  Pillow could not convert the image ({e}); saving it unchanged."))
    ext = guess_ext(data, content_type)
    path = folder / f"{entry_id}{ext}"
    path.write_bytes(data)
    return path.relative_to(ROOT).as_posix()


def guess_ext(data: bytes, content_type: str) -> str:
    if data[:3] == b"\xff\xd8\xff" or "jpeg" in content_type:
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n" or "png" in content_type:
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP" or "webp" in content_type:
        return ".webp"
    if data[:3] == b"GIF":
        return ".gif"
    return ".jpg"


def download_cover(url: str, entry_id: str) -> str:
    """Returns the relative cover path, or "" on failure (the site shows a placeholder)."""
    if not url:
        return ""
    print(C.dim(f"  Downloading cover … {url}"))
    try:
        resp = http_get(url)
    except ConnectionError as e:
        print(C.yellow(f"  Cover download failed: {e}  (a placeholder will be shown)"))
        return ""
    ctype = resp.headers.get("Content-Type", "")
    if not ctype.startswith("image/") and guess_ext(resp.content, "") == ".jpg" and resp.content[:3] != b"\xff\xd8\xff":
        print(C.yellow(f"  The URL did not return an image ({ctype or 'unknown type'}); skipping cover."))
        return ""
    return save_cover_bytes(resp.content, entry_id, ctype)


def import_cover(src: str, entry_id: str) -> str:
    """Manual mode: local file path or http(s) URL."""
    if not src:
        return ""
    if src.startswith(("http://", "https://")):
        return download_cover(src, entry_id)
    path = Path(src.strip('"\'')).expanduser()
    if not path.is_file():
        print(C.yellow(f"  File not found: {path}  (no cover saved)"))
        return ""
    if Image is None:
        target = entry_cover_dir(entry_id) / f"{entry_id}{path.suffix.lower() or '.jpg'}"
        shutil.copyfile(path, target)
        return target.relative_to(ROOT).as_posix()
    return save_cover_bytes(path.read_bytes(), entry_id)


# ====================================================================
# Main flow
# ====================================================================

def next_id(category: str, entries: list) -> str:
    numbers = [int(m.group(1)) for e in entries if (m := re.match(rf"^{category}-(\d+)$", str(e.get("id", ""))))]
    return f"{category}-{(max(numbers) + 1 if numbers else 1):04d}"


def norm(text) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().casefold()


def find_duplicate(entries: list, item: dict):
    src = item.get("source") or {}
    for e in entries:
        es = e.get("source") or {}
        if src.get("id") and es.get("provider") == src.get("provider") and str(es.get("id")) == str(src.get("id")):
            return e
        same_title = norm(item.get("title")) and norm(e.get("title")) == norm(item.get("title"))
        same_orig = norm(item.get("originalTitle")) and norm(e.get("originalTitle")) == norm(item.get("originalTitle"))
        if (same_title or same_orig) and e.get("year") == item.get("year"):
            return e
    return None


def choose_from_search(category: str):
    """Loop until the user picks a result, or returns None for manual mode."""
    while True:
        query = input(f"\n{C.bold('Search')} (title keywords, empty = manual mode): ").strip()
        if not query:
            return None
        try:
            print(C.dim("  Searching …"))
            results = search(category, query)
        except ConnectionError as e:
            print(C.red(f"  {e}"))
            if not ask_yes("  Try again?", True):
                return None
            continue
        if not results:
            print(C.yellow("  No results. Try other keywords (English or original title)."))
            continue

        print()
        rows = []
        for r in results:
            main = r["title"] or r["originalTitle"] or "?"
            orig = f"  {C.dim(r['originalTitle'])}" if r["originalTitle"] and r["originalTitle"] != r["title"] else ""
            meta = " · ".join(str(x) for x in (r.get("year"), r.get("creator") or r.get("creatorOriginal"), r.get("_extra")) if x)
            rows.append(f"{C.bold(main)}{orig}  {C.dim(meta)}")
        rows.append(C.dim("search again"))
        rows.append(C.dim("switch to manual mode"))
        idx = ask_choice("Pick a result", rows, 0)
        if idx == len(results):
            continue
        if idx == len(results) + 1:
            return None
        return details(category, results[idx])


def edit_fields(item: dict) -> dict:
    """Show every prefilled field and let the user keep (Enter), change, or clear ("-")."""
    print(f"\n{C.bold('Check the fields')}  {C.dim('(Enter = keep, type to change, - = clear)')}")
    while True:
        item["title"] = ask("English title (main title)", item.get("title", ""))
        if item["title"]:
            break
        print(C.yellow("  The English title is required (it's the main title on the site)."))
    if has_cjk(item["title"]):
        print(C.yellow("  Note: this title contains CJK characters. The site expects an English title here;"))
        print(C.yellow("        put the native title in “Original title”."))
    item["originalTitle"] = ask("Original title", item.get("originalTitle", ""))
    default_lang = item.get("originalLanguage") or guess_lang(item["originalTitle"])
    item["originalLanguage"] = ask_lang(default_lang) if item["originalTitle"] else ask_lang(default_lang or "")
    item["altTitles"] = ask_list("Other titles / translations", item.get("altTitles", []), ";")
    item["creator"] = ask("Creator (English name)", item.get("creator", ""))
    item["creatorOriginal"] = ask("Creator (original name)", item.get("creatorOriginal", ""))
    item["year"] = ask_year(item.get("year"))
    return item


def run(category: str | None, manual: bool) -> int:
    setup_console()
    print(C.bold("\nMEDIA LOG — add an entry") + C.dim("   (Ctrl+C to cancel at any time)\n"))
    if Image is None:
        print(C.dim("  Pillow not installed: covers will be saved without conversion.\n"))

    if category not in CATEGORIES:
        category = CATEGORIES[ask_choice("Category", CATEGORIES)]
    print(C.dim(f"  → {category}"))
    entries = load_entries(category)

    item = None if manual else choose_from_search(category)
    if item is None:
        print(C.dim("\n  Manual mode."))
        item = {"title": "", "originalTitle": "", "originalLanguage": "", "altTitles": [],
                "creator": "", "creatorOriginal": "", "year": None, "coverUrl": "", "source": None, "tags": []}

    item = edit_fields(item)

    dup = find_duplicate(entries, item)
    if dup:
        print(C.yellow(f"\n  Looks like a duplicate of {dup.get('id')}: {dup.get('title')} ({dup.get('year')})."))
        if not ask_yes("  Add it anyway?", False):
            print("Nothing was written.")
            return 0

    entry_id = next_id(category, entries)

    # Cover
    print()
    cover = ""
    if item.get("coverUrl"):
        if ask_yes(f"Download the cover from {item['source']['provider']}?", True):
            cover = download_cover(item["coverUrl"], entry_id)
    if not cover:
        src = ask("Cover: local file path or image URL (empty = placeholder)", "")
        cover = import_cover(src, entry_id)
    if cover:
        print(C.green(f"  Cover saved: {cover}"))

    # Personal fields
    print()
    rating = ask_rating()
    review = ask_review()
    is_light_novel = category == "literature" and (item.get("source") or {}).get("provider") == "anilist" and item.get("_extra") == "NOVEL"
    if item.get("_filteredTags"):
        print(C.dim(f"  (filtered out: {', '.join(item['_filteredTags'][:MAX_FILTERED_SHOWN])})"))
    auto_tags = item.get("tags") or []
    tags = ask_tags(["light novel", *auto_tags][:MAX_TAGS] if is_light_novel else auto_tags)
    date = ask_date()

    entry = {
        "id": entry_id,
        "title": item["title"],
        "originalTitle": item["originalTitle"],
        "originalLanguage": item["originalLanguage"],
        "altTitles": item["altTitles"],
        "creator": item["creator"],
        "creatorOriginal": item["creatorOriginal"],
        "year": item["year"],
        "date": date,
        "rating": rating,
        "review": review,
        "tags": tags,
        "cover": cover,
        "source": item.get("source"),
    }

    print(f"\n{C.bold('Summary')}")
    for key, value in entry.items():
        if value not in ("", None, []):
            shown = value if not isinstance(value, str) or "\n" not in value else value.replace("\n", " ⏎ ")
            print(f"  {C.dim(key.ljust(17))}{shown}")
    if not ask_yes("\nSave this entry?", True):
        if cover:
            (ROOT / cover).unlink(missing_ok=True)
        print("Nothing was written.")
        return 0

    path = save_entries(category, [*entries, entry])
    print(C.green(f"\n✓ Saved {entry_id} to {path.relative_to(ROOT)}"))
    print(C.dim("  Tip: run  python scripts/validate.py  and refresh the page."))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Add an entry to the media log.")
    parser.add_argument("-c", "--category", choices=CATEGORIES, help="skip the category menu")
    parser.add_argument("-m", "--manual", action="store_true", help="skip online search")
    args = parser.parse_args()
    try:
        return run(args.category, args.manual)
    except (KeyboardInterrupt, EOFError, Cancel):
        print(C.yellow("\n\nCancelled. Nothing was written."))
        return 1


if __name__ == "__main__":
    sys.exit(main())
