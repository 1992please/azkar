"""Check the transcribed book files for mistakes that tools can catch.

Usage: python tools/check.py            # every chapter that exists
       python tools/check.py adhan      # one chapter

Errors (exit code 1) must be fixed; warnings need a look.
Checks:
- index.tsv and chapters.tsv are well formed and consistent
- each chapter file has the required fields, and its pages and title match chapters.tsv
- entry numbers run without gaps or repeats, within and across chapters (a gap after a
  chapter that PROGRESS.md shows `in progress` is only a warning: the rest isn't saved yet)
- headings match the book's index (printed headings, since the index was printed from them),
  and every index heading of the chapter appears in it (in a chapter still in progress, only
  the headings on the pages before the last one saved)
- sub-heading letters (أ، ب، ج …) continue under the same heading and restart at أ under a
  new one (approved corrections applied) — this is how the p. 36 heading misprint showed up
- corrections are well formed and their printed text occurs exactly once
- the source's volume, page and hadith numbers are printed in the citation or the takhrij
- Arabic fields contain only expected characters (no Persian look-alikes, Latin letters,
  invisible characters or presentation forms)
- bold markers (**…**) are paired, and every entry text has its bold part marked
- the Sheikh's own text blocks (author_text) are well formed and placed after a real entry
"""

import argparse
import csv
import difflib
import json
import pathlib
import re
import sys
import unicodedata

from arabic import words
from book import BOOK_DIR, PROGRESS, corrected, field_value, statuses

ABJAD = "أ ب ج د هـ و ز ح ط ي ك ل م ن س ع ف ص ق ر ش ت ث خ ذ ض ظ غ".split()
GRADINGS = {"صحيح", "حسن", "صحيح لغيره", "حسن لغيره", "ضعيف", "صحيح موقوف", "حسن موقوف"}
COLLECTIONS = {
    # in the hadith databases
    "bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik", "ahmad", "darimi",
    # cited by the book but in neither database
    "ibnhibban", "abuawana", "nasai-kubra", "ibnsunni", "hakim", "tabarani", "bayhaqi",
    "ibnabishaybah", "abdurrazzaq", "ibnkhuzaymah", "bukhari-adab", "other",
}
ENTRY_FIELDS = {"number": int, "book_page": int, "heading": str, "citation": str, "source": dict,
                "text": str, "footnotes": list, "corrections": list, "transcriber_notes": list}
ARABIC_FIELDS = ["heading", "citation", "text", "grading", "takhrij"]
AUTHOR_KINDS = {"preface", "verses", "note", "list", "crossref", "essay", "heading"}
INDIC = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
AUTHOR_FIELDS = {"book_page": int, "heading": str, "kind": str, "text": str,
                 "footnotes": list, "corrections": list, "transcriber_notes": list}

ALLOWED = re.compile(
    "^["
    "ء-غف-ي"   # Arabic letters (no tatweel)
    "ً-ْٰ"          # tashkeel and dagger alif
    "٠-٩"                # Arabic-Indic digits
    "ﷺ"                       # ﷺ
    " «»﴿﴾()\\[\\]:،.؟!؛/*=…'\"-"  # punctuation the book uses
    "]*$")


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def error(self, where, msg):
        self.errors.append(f"ERROR   {where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"warning {where}: {msg}")


def norm(s: str) -> str:
    return " ".join(words(s))


def similar(a: str, b: str) -> bool:
    a, b = norm(a), norm(b)
    return a == b or (a and b and (a in b or b in a)) or difflib.SequenceMatcher(None, a, b).ratio() >= 0.8


ATTACHED_DASH = re.compile(r"-[^\s٠-٩-]|[^\s٠-٩-]-")


def bad_chars(s: str) -> list[str]:
    if ALLOWED.match(s):
        return []
    return sorted({f"U+{ord(c):04X} {unicodedata.name(c, '?')}" for c in s if not ALLOWED.match(c)})


def read_tsv(path: pathlib.Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def check_tables(r: Report) -> tuple[list[dict], list[dict]]:
    index = read_tsv(BOOK_DIR / "index.tsv")
    chapters = read_tsv(BOOK_DIR / "chapters.tsv")
    last = 0
    for i, row in enumerate(index, 2):
        where = f"index.tsv line {i}"
        if not row["page"].isdigit():
            r.error(where, f"page is not a number: {row['page']!r}")
            continue
        row["page"] = int(row["page"])
        if row["page"] < last:
            r.error(where, f"page {row['page']} is before the previous line's page {last}")
        last = row["page"]
        for c in bad_chars(row["title"]):
            r.error(where, f"unexpected character {c}")
    slugs = set()
    for i, ch in enumerate(chapters, 2):
        where = f"chapters.tsv line {i}"
        ch["from_page"], ch["to_page"] = int(ch["from_page"]), int(ch["to_page"])
        if ch["slug"] in slugs:
            r.error(where, f"duplicate slug {ch['slug']}")
        slugs.add(ch["slug"])
        rows = [k for k, row in enumerate(index) if row["page"] == ch["from_page"] and similar(row["title"], ch["title"])]
        if not rows:
            r.error(where, f"title not found in index.tsv at p. {ch['from_page']}")
        ch["index_row"] = rows[0] if rows else None
    for a, b in zip(chapters, chapters[1:]):
        if a["to_page"] != b["from_page"]:
            r.error("chapters.tsv", f"{a['slug']} ends at p. {a['to_page']} but {b['slug']} starts at p. {b['from_page']}")
    return index, chapters


def index_items(index: list[dict], chapters: list[dict], k: int) -> list[dict]:
    """Index rows that belong to chapter k (after its title row, before the next chapter's)."""
    start = chapters[k]["index_row"]
    end = chapters[k + 1]["index_row"] if k + 1 < len(chapters) else len(index)
    if start is None or end is None:
        return []
    return index[start + 1:end]


def check_chapter(r: Report, path: pathlib.Path, ch: dict, items: list[dict], in_progress: bool) -> list[int]:
    name = path.name
    book = json.loads(path.read_text(encoding="utf-8"))
    for key in ("chapter", "book_pages", "notes", "skipped", "author_text", "entries"):
        if key not in book:
            r.error(name, f"missing field {key!r}")
    if not similar(book.get("chapter", ""), ch["title"]):
        r.error(name, f"chapter title doesn't match chapters.tsv")
    lo, hi = ch["from_page"], ch["to_page"]
    pages = book.get("book_pages", [0, 0])
    if not (lo <= pages[0] <= pages[1] <= hi):
        r.error(name, f"book_pages {pages} outside the chapter's pages {lo}–{hi}")

    numbers, last_page = [], 0
    prev_label = None
    for e in book.get("entries", []):
        where = f"{name} entry {e.get('number', '?')}"
        for field, kind in ENTRY_FIELDS.items():
            if not isinstance(e.get(field), kind):
                r.error(where, f"field {field!r} missing or not a {kind.__name__}")
        if not isinstance(e.get("number"), int):
            continue
        numbers.append(e["number"])
        if not (pages[0] <= e["book_page"] <= pages[1]):
            r.error(where, f"book_page {e['book_page']} outside book_pages {pages}")
        if e["book_page"] < last_page:
            r.error(where, f"book_page {e['book_page']} is before the previous entry's page")
        last_page = e["book_page"]
        if e.get("grading") is None:
            if not any("grading" in n for n in e["transcriber_notes"]):
                r.warn(where, "no grading and no transcriber note explaining why")
        elif e["grading"] not in GRADINGS:
            r.warn(where, f"unusual grading {e['grading']!r}")
        if e["source"].get("collection") not in COLLECTIONS:
            r.error(where, f"unknown collection {e['source'].get('collection')!r} (add it to COLLECTIONS if it's new)")
        for key in ("volume", "page", "hadith"):
            value = e["source"].get(key)
            digits = str(value).translate(INDIC)
            if value is not None and not re.search(f"(?<![٠-٩]){digits}(?![٠-٩])", e["citation"] + " " + (e.get("takhrij") or "")):
                r.warn(where, f"source {key} {value} is printed neither in the citation nor in the takhrij")
        if "(*" in e["text"]:
            r.error(where, "footnote marker left in the text")
        check_bold(r, where, e["text"])
        if "**" not in e["text"]:
            r.warn(where, "no bold part marked")
        for field in ARABIC_FIELDS:
            value = e.get(field)
            for c in bad_chars(value) if isinstance(value, str) else []:
                r.error(where, f"unexpected character in {field}: {c}")
            if isinstance(value, str) and (value != value.strip() or "  " in value):
                r.warn(where, f"extra spaces in {field}")
            if isinstance(value, str) and ATTACHED_DASH.search(value.replace("*", "")):
                r.warn(where, f"a dash without a space on each side in {field}")
        for k, note in enumerate(e["footnotes"]):
            for c in bad_chars(note):
                r.error(where, f"unexpected character in footnote {k + 1}: {c}")
            if ATTACHED_DASH.search(note.replace("*", "")):
                r.warn(where, f"a dash without a space on each side in footnote {k + 1}")
        check_corrections(r, where, e)

        # Sub-heading letters, with approved heading corrections applied.
        heading = corrected(e, "heading")
        if e.get("label"):
            if e["label"] not in ABJAD:
                r.error(where, f"label {e['label']!r} is not an abjad letter")
            elif prev_label and prev_label[0] == heading:
                want = ABJAD[ABJAD.index(prev_label[1]) + 1]
                if e["label"] != want:
                    r.warn(where, f"label ({e['label']}) after ({prev_label[1]}) under the same heading; expected ({want})")
            elif e["label"] != ABJAD[0]:
                r.warn(where, f"label ({e['label']}) starts a new heading; expected (أ). "
                              "The heading may be misprinted, or this entry continues the previous heading")
            prev_label = (heading, e["label"])

    for a, b in zip(numbers, numbers[1:]):
        if b != a + 1:
            r.error(name, f"entry {b} follows entry {a}")
    check_author_text(r, name, book.get("author_text", []), numbers, pages)

    # Headings against the index (printed headings: the index was printed from them).
    first_page = {}
    for e in sorted(book.get("entries", []) + book.get("author_text", []), key=lambda x: x.get("book_page", 0)):
        if isinstance(e.get("heading"), str):  # a missing heading is reported above
            first_page.setdefault(e["heading"], e["book_page"])
    for heading, page in first_page.items():
        if similar(heading, ch["title"]):
            continue  # a chapter without sub-headings: its entries come under the chapter title
        hits = [it for it in items if similar(it["title"], heading)]
        if not hits:
            r.warn(name, f"heading not in the index: {heading}")
        elif not any(0 <= page - it["page"] <= 1 for it in hits):
            r.warn(name, f"heading «{heading}» is on p. {page}, index says p. {', '.join(str(h['page']) for h in hits)}")
    for it in items:
        if in_progress and it["page"] >= pages[1]:
            continue  # its page isn't saved yet, or only in part
        if not any(similar(it["title"], h) for h in first_page):
            r.warn(name, f"index heading not found in the chapter: {it['title']} (p. {it['page']})")
    return numbers


def check_bold(r: Report, where: str, text: str) -> None:
    """Bold runs are marked **like this**, the markers attached to the run's first and last word."""
    open_ = False
    for tok in text.split():
        if tok.startswith("**"):
            if open_:
                r.error(where, f"bold run opened twice (at {tok!r})")
            open_, tok = True, tok[2:]
        if tok.endswith("**"):
            if not open_:
                r.error(where, f"bold run closed without being opened (at {tok!r})")
            open_, tok = False, tok[:-2]
        if "*" in tok:
            r.error(where, f"stray * in {tok!r}")
    if open_:
        r.error(where, "bold run not closed")


def check_author_text(r: Report, name: str, blocks: list, numbers: list[int], pages: list[int]) -> None:
    for k, b in enumerate(blocks, 1):
        where = f"{name} author_text {k}"
        for field, kind in AUTHOR_FIELDS.items():
            if not isinstance(b.get(field), kind):
                r.error(where, f"field {field!r} missing or not a {kind.__name__}")
        if "after_entry" not in b or (b["after_entry"] is not None and b["after_entry"] not in numbers):
            r.error(where, "after_entry must be the number of an entry in this chapter, or null")
        if b.get("kind") not in AUTHOR_KINDS:
            r.error(where, f"kind must be one of {sorted(AUTHOR_KINDS)}")
        if isinstance(b.get("book_page"), int) and not (pages[0] <= b["book_page"] <= pages[1]):
            r.error(where, f"book_page {b['book_page']} outside book_pages {pages}")
        for field in ("heading", "text"):
            for c in bad_chars(b.get(field) or ""):
                r.error(where, f"unexpected character in {field}: {c}")
        check_bold(r, where, b.get("text") or "")
        if isinstance(b.get("corrections"), list):
            check_corrections(r, where, b)


def check_corrections(r: Report, where: str, e: dict) -> None:
    for c in e["corrections"]:
        for key in ("id", "field", "printed", "corrected", "confidence", "status", "reason"):
            if key not in c:
                r.error(where, f"correction missing {key!r}")
                return
        if c["status"] not in ("proposed", "approved", "rejected"):
            r.error(where, f"correction {c['id']}: bad status {c['status']!r}")
        decided_by = c.get("decided_by")
        if decided_by not in (None, "owner", "auto"):
            r.error(where, f"correction {c['id']}: decided_by must be owner, auto or null")
        if c["status"] != "proposed" and decided_by is None:
            r.error(where, f"correction {c['id']}: an approved or rejected correction needs decided_by")
        if c["status"] == "proposed" and decided_by is not None:
            r.error(where, f"correction {c['id']}: a proposed correction can't have decided_by")
        conf = c["confidence"]
        if not isinstance(conf, (int, float)) or not 0 <= conf <= 1:
            r.error(where, f"correction {c['id']}: confidence must be a number from 0 to 1")
        elif decided_by == "auto" and conf < 0.9:
            r.error(where, f"correction {c['id']}: approved automatically below 0.90")
        value = field_value(e, c["field"])
        if not isinstance(value, str) or value.count(c["printed"]) != 1:
            r.error(where, f"correction {c['id']}: printed text must occur exactly once in {c['field']}")
        for c2 in bad_chars(c["corrected"]):
            r.error(where, f"correction {c['id']}: unexpected character {c2}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*")
    args = parser.parse_args()

    r = Report()
    index, chapters = check_tables(r)
    progress = statuses(PROGRESS.read_text(encoding="utf-8")) if PROGRESS.exists() else {}
    in_progress = {slug for slug, status in progress.items() if status.startswith("in progress")}
    previous_last = previous_slug = None
    checked = 0
    for k, ch in enumerate(chapters):
        path = BOOK_DIR / f"{ch['slug']}.json"
        if not path.exists():
            previous_last = None
            continue
        if args.names and ch["slug"] not in args.names:
            previous_last = None
            continue
        numbers = check_chapter(r, path, ch, index_items(index, chapters, k), ch["slug"] in in_progress)
        checked += 1
        if numbers and previous_last is not None and numbers[0] != previous_last + 1:
            message = f"first entry {numbers[0]} doesn't follow the previous chapter's last entry {previous_last}"
            if numbers[0] > previous_last + 1 and previous_slug in in_progress:
                r.warn(path.name, f"{message} ({previous_slug} is still in progress)")
            else:
                r.error(path.name, message)
        previous_last, previous_slug = numbers[-1] if numbers else None, ch["slug"]

    known = {ch["slug"] for ch in chapters}
    for path in sorted(BOOK_DIR.glob("*.json")):
        if path.stem not in known:
            r.error(path.name, "file name is not a slug in chapters.tsv")

    for line in r.errors + r.warnings:
        print(line)
    print(f"{checked} chapter file(s) checked: {len(r.errors)} errors, {len(r.warnings)} warnings")
    sys.exit(1 if r.errors else 0)


if __name__ == "__main__":
    main()
