#!/usr/bin/env python3
"""
validate.py — check every data/*.json file for common mistakes.

Usage:
    python scripts/validate.py

ERRORS  (exit code 1): missing required fields, wrong types, bad rating,
                       bad date, missing cover file, duplicate id, bad language code.
WARNINGS (exit code 0): things that work but are probably not what you want,
                       e.g. a CJK `title` (the site expects an English title there).
"""

from __future__ import annotations

import datetime as dt
import json
import sys

from common import (
    CATEGORIES, COVERS_DIR, DATA_DIR, DATE_RE, FIELD_ORDER, LANG_RE, ROOT,
    REQUIRED_FIELDS, Colors, has_cjk, is_valid_rating, setup_console,
)

TITLE_MODES = {"english", "original", "both"}


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, where: str, msg: str):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str):
        self.warnings.append(f"{where}: {msg}")


def is_str_list(value) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def check_entry(entry, where: str, category: str, seen_ids: dict, used_covers: set, r: Report):
    if not isinstance(entry, dict):
        r.error(where, "entry must be a JSON object")
        return

    # --- required fields -------------------------------------------------
    for field in REQUIRED_FIELDS:
        if field not in entry or entry[field] in ("", None):
            r.error(where, f'missing required field "{field}"')

    eid = entry.get("id")
    if eid is not None:
        if not isinstance(eid, str):
            r.error(where, '"id" must be a string')
        else:
            if eid in seen_ids:
                r.error(where, f'duplicate id "{eid}" (also in {seen_ids[eid]})')
            else:
                seen_ids[eid] = where
            if not eid.startswith(category + "-"):
                r.warn(where, f'id "{eid}" does not start with "{category}-"')

    # --- titles ----------------------------------------------------------
    title = entry.get("title")
    if title is not None and not isinstance(title, str):
        r.error(where, '"title" must be a string')
    elif isinstance(title, str) and has_cjk(title):
        r.warn(where, f'title "{title}" contains CJK characters — '
                      "consider an English title and moving this to originalTitle")

    for field in ("originalTitle", "creator", "creatorOriginal", "review", "cover"):
        if field in entry and not isinstance(entry[field], str):
            r.error(where, f'"{field}" must be a string')

    lang = entry.get("originalLanguage")
    if lang not in (None, ""):
        if not isinstance(lang, str) or not LANG_RE.match(lang):
            r.error(where, f'originalLanguage "{lang}" is not a valid code '
                           '(examples: "ja", "zh", "zh-Hant", "ko", "fr", "pt-BR")')
    elif entry.get("originalTitle") and entry.get("originalTitle") != title:
        r.warn(where, "originalTitle is set but originalLanguage is empty "
                      "(the page will guess the script, but an explicit code is better)")

    for field in ("altTitles", "tags"):
        if field in entry and not is_str_list(entry[field]):
            r.error(where, f'"{field}" must be an array of strings, e.g. ["a", "b"]')

    # --- numbers & dates ---------------------------------------------------
    year = entry.get("year")
    if year not in (None, ""):
        if isinstance(year, bool) or not isinstance(year, int):
            r.error(where, f'"year" must be an integer, got {year!r}')
        elif not 1000 <= year <= dt.date.today().year + 5:
            r.warn(where, f"year {year} looks unusual")

    rating = entry.get("rating")
    if rating not in (None, "") and not is_valid_rating(rating):
        r.error(where, f"rating {rating!r} must be 1–5 in steps of 0.5 (1, 1.5, … 5)")

    date = entry.get("date")
    if date not in (None, ""):
        if not isinstance(date, str) or not DATE_RE.match(date):
            r.error(where, f'date "{date}" must use YYYY-MM-DD')
        else:
            try:
                d = dt.date.fromisoformat(date)
                if d > dt.date.today() + dt.timedelta(days=1):
                    r.warn(where, f"date {date} is in the future")
            except ValueError:
                r.error(where, f'date "{date}" is not a real calendar date')

    # --- cover -------------------------------------------------------------
    cover = entry.get("cover")
    if isinstance(cover, str) and cover:
        if cover.startswith(("http://", "https://")):
            r.error(where, "cover must be a local path (covers/…), not a URL — "
                           "the site never loads images from external servers")
        else:
            if not cover.startswith(f"covers/{category}/"):
                r.warn(where, f'cover "{cover}" is not in covers/{category}/')
            path = (ROOT / cover).resolve()
            if not path.is_file():
                r.error(where, f'cover file not found: "{cover}"')
            else:
                used_covers.add(path)

    source = entry.get("source")
    if source is not None and not isinstance(source, dict):
        r.error(where, '"source" must be an object like {"provider": "tmdb", "id": "129"}')

    unknown = [k for k in entry if k not in FIELD_ORDER]
    if unknown:
        r.warn(where, f"unknown field(s) {unknown} (ignored by the site — typo?)")


def check_settings(r: Report):
    path = DATA_DIR / "settings.json"
    if not path.exists():
        r.warn("settings.json", 'file missing — defaults are used ("titleMode": "both")')
        return
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        r.error("settings.json", f"invalid JSON: {e}")
        return
    mode = settings.get("titleMode", "both")
    if mode not in TITLE_MODES:
        r.error("settings.json", f'titleMode "{mode}" must be one of {sorted(TITLE_MODES)}')
    if "deviceTilt" in settings and not isinstance(settings["deviceTilt"], bool):
        r.error("settings.json", '"deviceTilt" must be true or false')


def main() -> int:
    setup_console()
    r = Report()
    seen_ids: dict[str, str] = {}
    used_covers: set = set()
    total = 0

    for category in CATEGORIES:
        path = DATA_DIR / f"{category}.json"
        name = path.name
        if not path.exists():
            r.error(name, "file is missing (create it with [] as content)")
            continue
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            r.error(name, f"invalid JSON: line {e.lineno}, column {e.colno}: {e.msg}")
            continue
        if not isinstance(entries, list):
            r.error(name, "top level must be an array [ … ]")
            continue
        for i, entry in enumerate(entries):
            label = entry.get("id", f"#{i}") if isinstance(entry, dict) else f"#{i}"
            check_entry(entry, f"{name} #{i + 1} [{label}]", category, seen_ids, used_covers, r)
        total += len(entries)

    check_settings(r)

    # Cover files nobody references (harmless, but wasted repo space).
    if COVERS_DIR.exists():
        for f in sorted(COVERS_DIR.rglob("*")):  # recursive: covers/<category>/ and loose files in covers/
            if f.is_file() and not f.name.startswith(".") and f.resolve() not in used_covers:
                r.warn("covers/", f'"{f.relative_to(COVERS_DIR).as_posix()}" is not used by any entry')

    for w in r.warnings:
        print(Colors.yellow("WARN  ") + w)
    for e in r.errors:
        print(Colors.red("ERROR ") + e)

    summary = f"{total} entries checked — {len(r.errors)} error(s), {len(r.warnings)} warning(s)"
    print()
    print(Colors.red(summary) if r.errors else Colors.green(summary))
    return 1 if r.errors else 0


if __name__ == "__main__":
    sys.exit(main())
