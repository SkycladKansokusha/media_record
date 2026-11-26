#!/usr/bin/env python3
"""
delete.py — interactively delete one entry and its cover, then close the gap in the numbering.

Usage:
    python scripts/delete.py              # pick a category, then an entry by number or (fuzzy) name
    python scripts/delete.py -c movie     # preselect the category
    python scripts/delete.py --dry-run    # same flow, but only show what would change

Nothing is changed until you type "confirm".
Every later entry of the same category moves up one number, cover file included:
movie-0057 → movie-0056, movie-0058 → movie-0057 … Earlier entries are not touched.
A cover is only renamed when it follows the covers/<category>/<id>.<ext> pattern.
"""

from __future__ import annotations

import argparse
import difflib
import re
import signal
import sys
import unicodedata
from pathlib import Path

from common import CATEGORIES, ROOT, Colors, load_entries, save_entries, setup_console

C = Colors
ID_RE = re.compile(rf"^({'|'.join(CATEGORIES)})-(\d+)$")
# The word that must be typed to delete.
CONFIRM_WORD = "confirm"
# How many search results are listed.
MAX_MATCHES = 10
# Minimum similarity (0–1) for a fuzzy, non-substring name match.
FUZZY_CUTOFF = 0.7


class PlanError(Exception):
    """The deletion cannot be done safely; nothing has been changed."""


class Cancel(Exception):
    """The user backed out; nothing has been changed."""


# ====================================================================
# Picking the entry
# ====================================================================

def ask(prompt: str) -> str:
    return input(prompt).strip()


def choose_category() -> str:
    print(C.bold("Categories:"))
    for i, cat in enumerate(CATEGORIES, 1):
        print(f"  {C.cyan(str(i)):>4}  {cat:<11} {len(load_entries(cat))} entries")
    while True:
        raw = ask("Category (number or name, empty to quit): ").lower()
        if not raw:
            raise Cancel
        if raw.isdigit() and 1 <= int(raw) <= len(CATEGORIES):
            return CATEGORIES[int(raw) - 1]
        if raw in CATEGORIES:
            return raw
        print(C.yellow(f"  Please enter 1–{len(CATEGORIES)} or one of: {', '.join(CATEGORIES)}."))


def norm(text) -> str:
    """Lowercase, accents removed, punctuation and spaces dropped: "Amélie" → "amelie"."""
    text = unicodedata.normalize("NFKD", str(text or "")).casefold()
    return "".join(ch for ch in text if ch.isalnum())


def names_of(entry: dict) -> list[str]:
    return [n for n in [entry.get("title"), entry.get("originalTitle"), *(entry.get("altTitles") or [])] if n]


def search(entries: list, query: str) -> list[dict]:
    """Substring matches (shortest title first); only when there are none, fuzzy matches by similarity."""
    q = norm(query)
    if not q:
        return []
    words = [w for w in (norm(part) for part in query.split()) if w]  # "lord rings" → both words anywhere
    scored = []
    for e in entries:
        names = [norm(n) for n in names_of(e)]
        hits = [n for n in names if q in n or (len(words) > 1 and all(w in n for w in words))]
        if hits:
            scored.append((2.0, -min(len(n) for n in hits), e))
            continue
        best = max((difflib.SequenceMatcher(None, q, n).ratio() for n in names), default=0)
        # Also compare with same-length windows, so "hobit" finds "The Hobbit: An Unexpected Journey".
        for n in names:
            for i in range(max(1, len(n) - len(q) + 1)):
                best = max(best, difflib.SequenceMatcher(None, q, n[i:i + len(q) + 1]).ratio())
        if best >= FUZZY_CUTOFF:
            scored.append((best, 0, e))
    if any(s[0] == 2.0 for s in scored):  # exact substring hits make fuzzy ones noise
        scored = [s for s in scored if s[0] == 2.0]
    scored.sort(key=lambda s: (-s[0], -s[1]))
    return [e for _, _, e in scored[:MAX_MATCHES]]


def describe(entry: dict) -> str:
    original = entry.get("originalTitle")
    extra = f" / {original}" if original and original != entry.get("title") else ""
    return f"{entry['id']}  {entry.get('title', '')}{extra} ({entry.get('year', '?')})"


def choose_entry(category: str, entries: list) -> dict:
    by_id = {e.get("id"): e for e in entries}
    while True:
        raw = ask(f"Number or name in {category} (e.g. 56 or {category}-0056; empty to quit): ")
        if not raw:
            raise Cancel
        if raw.isdigit() and f"{category}-{int(raw):04d}" in by_id:
            return by_id[f"{category}-{int(raw):04d}"]
        if raw in by_id:
            return by_id[raw]
        matches = search(entries, raw)
        if not matches:
            print(C.yellow("  No entry matches. Try another number or name."))
            continue
        for i, e in enumerate(matches, 1):
            print(f"  {C.cyan(str(i)):>4}  {describe(e)}")
        pick = ask("Pick a result (number, empty to search again): ")
        if pick.isdigit() and 1 <= int(pick) <= len(matches):
            return matches[int(pick) - 1]


def own_cover(entry: dict, category: str) -> tuple[Path, str] | None:
    """(file, extension) when the cover is named after the entry id, else None."""
    cover = entry.get("cover") or ""
    m = re.match(rf"^covers/{category}/{re.escape(entry['id'])}(\.[A-Za-z0-9]+)$", cover)
    return (ROOT / cover, m.group(1)) if m else None


def make_plan(category: str, target_id: str) -> dict:
    """An id outside the <category>-NNNN pattern is deleted without renumbering anything."""
    entries = load_entries(category)
    m = ID_RE.match(target_id)
    number = int(m.group(2)) if m and m.group(1) == category else float("inf")
    target = next((e for e in entries if e.get("id") == target_id), None)
    if target is None:
        raise PlanError(f"{target_id} not found in data/{category}.json")

    # Delete the target's cover only if no other entry uses the same file.
    cover = target.get("cover") or ""
    shared = any(e is not target and e.get("cover") == cover for e in entries)
    delete_cover = ROOT / cover if cover and not shared else None

    moves = []  # (entry, new id, old cover file, new cover file, new cover field)
    for e in entries:
        m = ID_RE.match(str(e.get("id", "")))
        if not m or m.group(1) != category or int(m.group(2)) <= number:
            continue
        new_id = f"{category}-{int(m.group(2)) - 1:04d}"
        found = own_cover(e, category)
        if found:
            src, ext = found
            if not src.is_file():
                raise PlanError(f"cover of {e['id']} is missing: {e['cover']} (fix it first, then run again)")
            field = f"covers/{category}/{new_id}{ext}"
            moves.append((e, new_id, src, ROOT / field, field))
        else:
            moves.append((e, new_id, None, None, None))
    moves.sort(key=lambda mv: int(ID_RE.match(mv[0]["id"]).group(2)))  # ascending: each target slot is free

    # Final ids must stay unique; a cover rename may only land on a file that is moved or deleted first.
    renamed = {id(mv[0]): mv[1] for mv in moves}
    final_ids = [renamed.get(id(e), e["id"]) for e in entries if e is not target]
    if len(final_ids) != len(set(final_ids)):
        raise PlanError(f"renumbering would create duplicate ids in {category}; check the ids first")
    freed = {mv[2].resolve() for mv in moves if mv[2]} | ({delete_cover.resolve()} if delete_cover else set())
    for _, _, src, dst, _ in moves:
        if dst and dst.exists() and dst.resolve() not in freed:
            raise PlanError(f"{dst.relative_to(ROOT)} already exists and is not used by a moved entry")

    return {"category": category, "entries": entries, "target": target,
            "delete_cover": delete_cover, "shared_cover": shared, "moves": moves}


def print_plan(plan: dict) -> None:
    t = plan["target"]
    print(C.bold(f"Delete: {t['id']}  {t.get('title', '')} ({t.get('year', '?')})"))
    if plan["delete_cover"]:
        rel = plan["delete_cover"].relative_to(ROOT)
        state = "delete" if plan["delete_cover"].exists() else "already missing"
        print(f"  cover: {rel} ({state})")
    elif plan["shared_cover"]:
        print(f"  cover: {t['cover']} (kept, another entry uses it)")
    else:
        print("  cover: none")
    if not plan["moves"]:
        print("No later entries; nothing to renumber.")
        return
    print(f"Renumber {len(plan['moves'])} later entr{'y' if len(plan['moves']) == 1 else 'ies'}:")
    for e, new_id, src, _, field in plan["moves"]:
        note = "" if src else C.dim("  (cover not renamed)")
        print(f"  {e['id']} → {new_id}  {e.get('title', '')}{note}")


def apply_plan(plan: dict) -> None:
    signal.signal(signal.SIGINT, signal.SIG_IGN)  # don't stop halfway between files and JSON
    try:
        if plan["delete_cover"] and plan["delete_cover"].exists():
            plan["delete_cover"].unlink()
        for e, new_id, src, dst, field in plan["moves"]:
            if src:
                src.rename(dst)
                e["cover"] = field
            e["id"] = new_id
        save_entries(plan["category"], [e for e in plan["entries"] if e is not plan["target"]])
    finally:
        signal.signal(signal.SIGINT, signal.default_int_handler)


def main() -> int:
    setup_console()
    parser = argparse.ArgumentParser(description="Interactively delete an entry and its cover, then renumber the later entries.")
    parser.add_argument("-c", "--category", choices=CATEGORIES, help="skip the category menu")
    parser.add_argument("--dry-run", action="store_true", help="only show what would change")
    args = parser.parse_args()

    try:
        category = args.category or choose_category()
        entry = choose_entry(category, load_entries(category))
        print()
        plan = make_plan(category, entry["id"])
        print_plan(plan)
        if args.dry_run:
            print(C.dim("\nDry run: nothing was changed."))
            return 0
        answer = ask(f'\nType "{CONFIRM_WORD}" to delete, anything else to cancel: ')
        if answer.lower() != CONFIRM_WORD:
            raise Cancel
    except PlanError as e:
        print(C.red(f"ERROR: {e}"))
        return 1
    except (Cancel, KeyboardInterrupt, EOFError):
        print(C.yellow("\nCancelled. Nothing was changed."))
        return 1

    apply_plan(plan)
    print(C.green(f"\nDone: data/{plan['category']}.json saved."))
    print("Check with:  python3 scripts/validate.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
