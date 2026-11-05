#!/usr/bin/env python3
"""
backfill_tags.py — overwrite the tags of existing entries using their `source` id.

Usage:
    python scripts/backfill_tags.py                # dry-run: preview only, writes nothing
    python scripts/backfill_tags.py --apply        # back up, then write the changes
    python scripts/backfill_tags.py -c movie tv    # only these categories (default: movie tv anime manga)
    python scripts/backfill_tags.py --limit 3      # only the first N entries of each category

Candidates are looked up by id, never by searching. An entry keeps its current tags
when it has no source, the lookup fails, or nothing survives the filter in add.py.

TMDB needs the env var TMDB_API_KEY (v3 key or v4 read token); without it tmdb entries are skipped.
"""

from __future__ import annotations

import argparse
import collections
import copy
import datetime as dt
import os
import shutil
import signal
import subprocess
import sys
import time

import requests

from add import (
    ANILIST_API, HEADERS, MAX_TAGS, TIMEOUT, TMDB_API, anilist_tags, filter_tags,
)
from common import (
    CATEGORIES, ROOT, data_file, load_entries, ordered_entry, save_entries, setup_console,
)

# Categories processed when -c is not given.
DEFAULT_CATEGORIES = ["movie", "tv", "anime", "manga"]
# Categories whose book / music providers may be used; they only run when named with -c.
EXPLICIT_ONLY_CATEGORIES = {"literature", "music"}
# Minimum seconds between two HTTP requests.
REQUEST_INTERVAL = 0.4
# Minimum seconds between AniList requests; its rate limit is about 30 requests per minute.
ANILIST_REQUEST_INTERVAL = 2.5
# Seconds to wait after an HTTP 429 before trying again.
RATE_LIMIT_WAIT = 20
# How many times a request is retried after an HTTP 429.
RATE_LIMIT_RETRIES = 3
# iTunes stores tried in turn; a lookup only finds albums sold in that store.
ITUNES_STORES = ["US", "JP", "KR", "TW"]
# GraphQL query for one AniList work, by id.
ANILIST_BY_ID_QUERY = """
query ($id: Int) {
  Media(id: $id) {
    genres
    tags { name rank isMediaSpoiler isGeneralSpoiler }
  }
}
"""


class FetchError(Exception):
    """A lookup failed; the message is the reason shown in the report (never contains the API key)."""


# ====================================================================
# HTTP
# ====================================================================

_last_request = 0.0


def request_json(method: str, url: str, interval: float = REQUEST_INTERVAL, **kwargs):
    """Rate-limited request. Exception text is not reused: a requests error can quote the URL and its api_key."""
    global _last_request
    headers = {**HEADERS, **kwargs.pop("headers", {})}
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        time.sleep(max(0.0, _last_request + interval - time.monotonic()))
        _last_request = time.monotonic()
        try:
            resp = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
        except requests.RequestException as e:
            raise FetchError(f"network error: {e.__class__.__name__}") from None
        if resp.status_code == 429:
            if attempt < RATE_LIMIT_RETRIES:
                print(f"    HTTP 429, waiting {RATE_LIMIT_WAIT}s (retry {attempt + 1}/{RATE_LIMIT_RETRIES})...", flush=True)
                time.sleep(RATE_LIMIT_WAIT)
                continue
            raise FetchError(f"HTTP 429: still rate limited after {RATE_LIMIT_RETRIES} retries")
        if not resp.ok:
            raise FetchError(f"HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError:
            raise FetchError("invalid response: not JSON") from None
    raise AssertionError("unreachable")


# ====================================================================
# Candidate tags by id
# ====================================================================

def fetch_tmdb(kind: str, source_id: str) -> list:
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        raise FetchError("no TMDB_API_KEY")
    params, headers = {"language": "en-US"}, {}
    if key.startswith("eyJ"):  # v4 "API Read Access Token"
        headers["Authorization"] = f"Bearer {key}"
    else:  # v3 API key
        params["api_key"] = key
    info = request_json("GET", f"{TMDB_API}/{kind}/{source_id}", params=params, headers=headers)
    return [g.get("name") for g in info.get("genres") or []]


def fetch_anilist(source_id: str) -> list:
    try:
        variables = {"id": int(source_id)}
    except ValueError:
        raise FetchError(f"invalid AniList id: {source_id}") from None
    data = request_json("POST", ANILIST_API, interval=ANILIST_REQUEST_INTERVAL,
                        json={"query": ANILIST_BY_ID_QUERY, "variables": variables},
                        headers={"Accept": "application/json"})
    media = (data.get("data") or {}).get("Media")
    if not media:
        raise FetchError("AniList returned no media")
    return anilist_tags(media)


def fetch_openlibrary(source_id: str) -> list:
    return request_json("GET", f"https://openlibrary.org/works/{source_id}.json").get("subjects") or []


def fetch_googlebooks(source_id: str) -> list:
    info = request_json("GET", f"https://www.googleapis.com/books/v1/volumes/{source_id}").get("volumeInfo") or {}
    # Categories look like "Fiction / Fantasy / General".
    return [part.strip() for cat in info.get("categories") or [] for part in cat.split("/")]


def fetch_itunes(source_id: str) -> list:
    for store in ITUNES_STORES:
        results = request_json("GET", "https://itunes.apple.com/lookup",
                               params={"id": source_id, "country": store}).get("results") or []
        if results:
            return [results[0].get("primaryGenreName")]
    return []


def fetch_candidates(category: str, provider: str, source_id: str) -> list:
    if provider == "tmdb" and category in ("movie", "tv"):
        return fetch_tmdb(category, source_id)
    if provider == "anilist":
        return fetch_anilist(source_id)
    if category in EXPLICIT_ONLY_CATEGORIES:
        if provider == "openlibrary":
            return fetch_openlibrary(source_id)
        if provider == "googlebooks":
            return fetch_googlebooks(source_id)
        if provider == "itunes":
            return fetch_itunes(source_id)
    raise FetchError(f"unsupported provider for {category}: {provider}")


def cached_candidates(cache: dict, category: str, provider: str, source_id: str) -> list:
    """Each work is requested once; failures are remembered too.
    TMDB movie and tv ids are separate number spaces, so the kind is part of the tmdb key."""
    key = (provider, category if provider == "tmdb" else "", source_id)
    if key not in cache:
        try:
            cache[key] = fetch_candidates(category, provider, source_id)
        except FetchError as e:
            cache[key] = e
    if isinstance(cache[key], FetchError):
        raise cache[key]
    return cache[key]


# ====================================================================
# Processing
# ====================================================================

def fmt_list(items: list) -> str:
    return "[" + ", ".join(items) + "]"


def same_tags(old: list, new: list) -> bool:
    return [t.casefold() for t in old] == [t.casefold() for t in new]


class Report:
    def __init__(self):
        self.updated = 0
        self.unchanged = 0
        self.manual: list[tuple] = []
        self.not_updated: list[tuple] = []


def process_entry(entry: dict, category: str, cache: dict, report: Report) -> list | None:
    """Returns the new tags when the entry should be overwritten, else None."""
    eid, title = entry.get("id", "?"), entry.get("title", "")
    old = entry.get("tags") or []
    source = entry.get("source") or {}
    provider, source_id = source.get("provider"), str(source.get("id") or "")
    if not provider or not source_id:
        report.manual.append((category, eid, title, old))
        return None
    try:
        raw = cached_candidates(cache, category, provider, source_id)
    except FetchError as e:
        report.not_updated.append((category, eid, title, old, str(e)))
        return None
    new, filtered = filter_tags(raw, category, MAX_TAGS)
    if not new:
        names = list(dict.fromkeys(t for t in raw if isinstance(t, str)))
        reason = f"all candidates filtered: {fmt_list(names)}" if names else "no candidates returned"
        report.not_updated.append((category, eid, title, old, reason))
        return None
    if same_tags(old, new):
        report.unchanged += 1
        return None
    report.updated += 1
    print(f"{eid}  {title}")
    hint = f"     filtered out: {', '.join(filtered)}" if filtered else ""
    print(f"    {fmt_list(old)} → {fmt_list(new)}{hint}", flush=True)
    return new


def check_only_tags_changed(category: str, before: list, after: list) -> None:
    """Checks what save_entries would write against the file's current content; raises ValueError on any difference."""
    if len(before) != len(after):
        raise ValueError(f"{category}: entry count changed ({len(before)} → {len(after)})")
    written = sorted(after, key=lambda e: (e.get("date", ""), e.get("id", "")), reverse=True)
    written = [ordered_entry(e) for e in written]
    for old, new in zip(before, written):
        old_rest = {k: v for k, v in old.items() if k != "tags"}
        new_rest = {k: v for k, v in new.items() if k != "tags"}
        if old_rest != new_rest or list(old_rest) != list(new_rest):
            raise ValueError(f"{category}: {old.get('id')} would change outside tags, or entries would be reordered")


def write_changes(changes: dict) -> int:
    """changes: category -> (entries as loaded, entries with new tags). Nothing is written unless all pass."""
    try:
        for category, (before, after) in changes.items():
            check_only_tags_changed(category, before, after)
    except ValueError as e:
        print(f"\nERROR: safety check failed, nothing was written. {e}", file=sys.stderr)
        return 1

    backup = ROOT / f"data_backup_{dt.datetime.now():%Y%m%d-%H%M%S}"
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # the backup and all files go through, or none do
    backup.mkdir()
    for category in changes:
        shutil.copy2(data_file(category), backup / data_file(category).name)
    for category, (_, after) in changes.items():
        save_entries(category, after)
    signal.signal(signal.SIGINT, signal.default_int_handler)

    print(f"\nBackup: {backup.name}/ ({len(changes)} file(s))")
    print(f"Wrote: {', '.join(data_file(c).name for c in changes)}")
    ignored = subprocess.run(["git", "check-ignore", "-q", backup.name], cwd=ROOT, capture_output=True).returncode == 0
    if not ignored:
        print(f"WARNING: {backup.name}/ is not ignored by .gitignore. Do not commit it by accident.")
    return 0


def print_report(report: Report, apply: bool) -> None:
    print("\nNeeds manual handling (no source):")
    for category, eid, title, tags in report.manual:
        print(f"  {category}  {eid}  {title}  {fmt_list(tags)}")
    if not report.manual:
        print("  (none)")

    print("\nNot updated (tags kept):")
    for category, eid, title, tags, reason in report.not_updated:
        print(f"  {category}  {eid}  {title}  {fmt_list(tags)}  -- {reason}")
    if not report.not_updated:
        print("  (none)")

    print("\nSummary:")
    print(f"  {'Updated' if apply else 'Would update'}: {report.updated}")
    print(f"  No change: {report.unchanged}")
    print(f"  Needs manual handling: {len(report.manual)}")
    print(f"  Not updated: {len(report.not_updated)}")
    reasons = collections.Counter(item[4].split(":")[0] for item in report.not_updated)
    for reason, count in reasons.most_common():
        print(f"    {reason}: {count}")


def positive_int(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description="Overwrite entry tags using the id in their source (dry-run by default).")
    parser.add_argument("--apply", action="store_true", help="write the changes (default: preview only)")
    parser.add_argument("-c", "--category", nargs="+", choices=CATEGORIES, default=DEFAULT_CATEGORIES,
                        help="categories to process (default: movie tv anime manga)")
    parser.add_argument("--limit", type=positive_int, help="only process the first N entries of each category")
    args = parser.parse_args()

    report, cache, changes = Report(), {}, {}
    try:
        for category in dict.fromkeys(args.category):
            before = load_entries(category)
            after = copy.deepcopy(before)
            print(f"== {category} ==")
            changed = False
            for entry in after[:args.limit]:
                new = process_entry(entry, category, cache, report)
                if new is not None:
                    entry["tags"] = new
                    changed = True
            if changed:
                changes[category] = (before, after)
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was written.")
        return 130

    print_report(report, args.apply)
    if not args.apply:
        print("\nRun again with --apply to write changes.")
        return 0
    if not changes:
        print("\nNothing to write.")
        return 0
    return write_changes(changes)


if __name__ == "__main__":
    sys.exit(main())
