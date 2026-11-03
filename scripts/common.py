"""
common.py — helpers shared by add.py and validate.py.

Only uses the Python standard library, so validate.py can run anywhere
(including GitHub Actions) without installing anything.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

# Repository root = the folder that contains index.html (one level above scripts/).
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
COVERS_DIR = ROOT / "covers"

# Category id -> JSON file. Keep in sync with CATEGORIES in js/config.js.
CATEGORIES = ["movie", "tv", "anime", "manga", "literature", "music"]

REQUIRED_FIELDS = ["id", "title", "year", "date", "rating"]
OPTIONAL_FIELDS = [
    "originalTitle", "originalLanguage", "altTitles", "creator",
    "creatorOriginal", "review", "tags", "cover", "source",
]
# Order used when writing entries back to JSON, so files stay tidy and diff-friendly.
FIELD_ORDER = [
    "id", "title", "originalTitle", "originalLanguage", "altTitles",
    "creator", "creatorOriginal", "year", "date", "rating",
    "review", "tags", "cover", "source",
]

# BCP 47 subset: "ja", "zh", "zh-Hant", "zh-TW", "pt-BR", "es-419", "yue"...
LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Z][a-z]{3})?(-([A-Z]{2}|\d{3}))?$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Han ideographs, kana, hangul, CJK punctuation / full-width forms.
CJK_RE = re.compile(
    "[　-〿぀-ヿ㐀-䶿一-鿿"
    "가-힯豈-﫿＀-￯]"
)
KANA_RE = re.compile("[぀-ヿ]")
HANGUL_RE = re.compile("[ᄀ-ᇿ㄰-㆏가-힯]")
HAN_RE = re.compile("[㐀-䶿一-鿿豈-﫿]")


def has_cjk(text: str) -> bool:
    return bool(text and CJK_RE.search(text))


def guess_lang(text: str) -> str:
    """Rough script-based guess: kana -> ja, hangul -> ko, han only -> zh, else ''."""
    if not text:
        return ""
    if KANA_RE.search(text):
        return "ja"
    if HANGUL_RE.search(text):
        return "ko"
    if HAN_RE.search(text):
        return "zh"
    return ""


def is_valid_rating(value) -> bool:
    """1–5, in steps of 0.5 (1, 1.5, 2 … 5). bool is rejected even though it's an int."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return 1 <= value <= 5 and float(value * 2).is_integer()


def data_file(category: str) -> Path:
    return DATA_DIR / f"{category}.json"


def cover_dir(category: str) -> Path:
    """covers/<category>/ — created if missing."""
    path = COVERS_DIR / category
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_entries(category: str) -> list:
    path = data_file(category)
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ordered_entry(entry: dict) -> dict:
    """Return a copy with keys in FIELD_ORDER; empty optional values are dropped."""
    out = {}
    for key in FIELD_ORDER:
        if key not in entry:
            continue
        value = entry[key]
        if key not in REQUIRED_FIELDS and value in ("", None, [], {}):
            continue
        out[key] = value
    for key, value in entry.items():  # keep any custom fields at the end
        if key not in out and key not in FIELD_ORDER:
            out[key] = value
    return out


def save_entries(category: str, entries: list) -> Path:
    """
    Write entries sorted by date (newest first), pretty-printed, with
    ensure_ascii=False so 千と千尋 stays readable instead of \\u5343...
    Written to a temp file first, then swapped in, so a crash can't leave half a file.
    """
    entries = sorted(entries, key=lambda e: (e.get("date", ""), e.get("id", "")), reverse=True)
    entries = [ordered_entry(e) for e in entries]
    path = data_file(category)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    return path


def setup_console() -> None:
    """Make sure CJK text prints correctly on Windows consoles."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


class Colors:
    """Tiny ANSI color helper; disabled when output is not a terminal."""
    enabled = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None

    @classmethod
    def wrap(cls, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if cls.enabled else text

    @classmethod
    def red(cls, t): return cls.wrap("31", t)
    @classmethod
    def yellow(cls, t): return cls.wrap("33", t)
    @classmethod
    def green(cls, t): return cls.wrap("32", t)
    @classmethod
    def cyan(cls, t): return cls.wrap("36", t)
    @classmethod
    def dim(cls, t): return cls.wrap("2", t)
    @classmethod
    def bold(cls, t): return cls.wrap("1", t)
