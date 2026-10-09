"""Cross-check a chapter's transcription against OCR of the pages.

Usage: python tools/ocr_check.py adhan [--file other.json] [--crops]

Run tools/ocr.py on the chapter's pages and tools/match.py first.
Each word of the printed headings, citations, entry texts and the Sheikh's own
text (author_text) is compared with the OCR word at the same place, and with
the matched database hadith (footnotes are not checked):

  confirmed   OCR reads the same word.
  memory      OCR differs while my word agrees with the database: the pattern
              of writing the familiar wording instead of what is printed.
  mine        OCR and the database agree with each other against my word:
              probably my misreading.
  ocr-only    OCR differs and there is no database word to compare (or it
              differs too).
  order       my word has no OCR word at its place, but the OCR has it one or
              two words away: words may be swapped.

"memory" and "ocr-only" are listed only when the OCR is confident (OCR misreads
are common at low confidence; the real errors in the pilot were all read at 81+).

The last three must be checked on a zoomed scan. --crops saves a zoomed image
of each one's line to .cache/ocr/flags/<chapter>/. Results go to
.cache/reports/<chapter>-ocr.json.
"""

import argparse
import difflib
import json
import pathlib

import pymupdf

from arabic import normalize_word
from book import BOOK_DIR, load_chapter
from ocr import DPI, PDF, words as ocr_words

ROOT = pathlib.Path(__file__).resolve().parent.parent
SALUTATION = "ﷺ"
CONFIDENT = 80  # Tesseract word confidence above which an OCR difference is listed
WINDOW = 2      # how far to look for a swapped word


def my_tokens(book: dict) -> list[dict]:
    """Printed words in reading order: each new heading, then each entry's citation and text,
    with the Sheikh's own text blocks (author_text) after the entry they follow."""
    blocks = {}
    for b in book.get("author_text", []):
        blocks.setdefault(b["after_entry"], []).append(b)
    items = [(0, "author_text", b) for b in blocks.get(None, [])]
    for e in book["entries"]:
        items.append((e["number"], "entry", e))
        items += [(e["number"], "author_text", b) for b in blocks.get(e["number"], [])]

    out, heading = [], None
    for number, kind, item in items:
        if kind == "entry":
            fields = [("citation", item["citation"]), ("text", item["text"]), ("grading", item.get("grading") or "")]
        else:
            fields = [("author_text", item["text"])]
        if item["heading"] != heading:
            fields.insert(0, ("heading", item["heading"]))
            heading = item["heading"]
        for field, value in fields:
            for i, tok in enumerate(value.split()):
                n = normalize_word(tok)
                if n and tok != SALUTATION:
                    out.append({"entry": number, "field": field, "index": i, "text": tok, "norm": n})
    return out


def db_words(book: dict, matches: dict) -> dict:
    """For each (entry, token index) of the text, the matched database word there, if any."""
    out = {}
    results = {r["number"]: r for r in matches["results"]}
    for e in book["entries"]:
        m = results.get(e["number"], {}).get("match")
        if not m:
            continue
        mine = [(i, normalize_word(t)) for i, t in enumerate(e["text"].split())]
        mine = [(i, n) for i, n in mine if n]
        db = [n for n in (normalize_word(t) for t in m["text"].split()) if n]
        sm = difflib.SequenceMatcher(None, [n for _, n in mine], db, autojunk=False)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
                for k in range(i2 - i1):
                    out[(e["number"], mine[i1 + k][0])] = db[j1 + k]
    return out


def align(mine: list[dict], ocr: list[dict]) -> None:
    """Attach the OCR word that lines up with each of my words (or None)."""
    sm = difflib.SequenceMatcher(None, [t["norm"] for t in mine], [o["norm"] for o in ocr], autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal" or (tag == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                mine[i1 + k]["ocr"] = ocr[j1 + k]
                mine[i1 + k]["ocr_index"] = j1 + k
        elif tag == "replace":
            for t in mine[i1:i2]:
                j = max(range(j1, j2), key=lambda j: difflib.SequenceMatcher(None, t["norm"], ocr[j]["norm"]).ratio())
                if difflib.SequenceMatcher(None, t["norm"], ocr[j]["norm"]).ratio() >= 0.5:
                    t["ocr"], t["ocr_index"] = ocr[j], j
    # A word with no OCR partner that the OCR has a word or two away: possibly swapped words.
    last = 0
    for t in mine:
        if "ocr_index" in t:
            last = t["ocr_index"]
            continue
        near = [j for j in range(max(0, last - WINDOW), min(len(ocr), last + WINDOW + 2)) if ocr[j]["norm"] == t["norm"]]
        if near:
            t["ocr"], t["swapped"] = ocr[near[0]], True


def classify(t: dict, db: str | None) -> str:
    o = t.get("ocr")
    if o is None:
        return "no-ocr"
    if t.get("swapped"):
        return "order"
    if o["norm"] == t["norm"]:
        return "confirmed"
    if db is not None and db == o["norm"]:
        return "mine"
    if o["conf"] < CONFIDENT:
        return "ocr-noise"
    if db is not None and db == t["norm"]:
        return "memory"
    return "ocr-only"


def save_crop(doc, t: dict, ocr: list[dict], path: pathlib.Path) -> None:
    o = t["ocr"]
    line = [w for w in ocr if w["page"] == o["page"] and w["line"] == o["line"]]
    x0 = min(w["box"][0] for w in line) - 20
    y0 = min(w["box"][1] for w in line) - 25
    x1 = max(w["box"][0] + w["box"][2] for w in line) + 20
    y1 = max(w["box"][1] + w["box"][3] for w in line) + 25
    scale = 72 / DPI
    clip = pymupdf.Rect(x0 * scale, y0 * scale, x1 * scale, y1 * scale)
    doc[o["page"] - 1].get_pixmap(dpi=DPI, clip=clip).save(path)


def save_sheets(crops: list[pathlib.Path], out_dir: pathlib.Path, per_sheet: int = 8) -> list[pathlib.Path]:
    """Stack the line crops into a few tall images, in the order of the printed list."""
    sheets = []
    for start in range(0, len(crops), per_sheet):
        pix = [pymupdf.Pixmap(str(c)) for c in crops[start:start + per_sheet]]
        gap = 12
        width = max(p.width for p in pix)
        height = sum(p.height + gap for p in pix)
        sheet = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, width, height), False)
        sheet.clear_with(200)
        y = 0
        for p in pix:
            if p.n != 3 or p.alpha:
                p = pymupdf.Pixmap(pymupdf.csRGB, p, 0)
            p.set_origin(width - p.width, y)
            sheet.copy(p, p.irect)
            y += p.height + gap
        path = out_dir / f"sheet-{start // per_sheet + 1}.png"
        sheet.save(path)
        sheets.append(path)
    return sheets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--file", type=pathlib.Path, help="check this chapter file instead")
    parser.add_argument("--crops", action="store_true")
    args = parser.parse_args()

    book = json.loads(args.file.read_text(encoding="utf-8")) if args.file else load_chapter(args.name)
    matches = json.loads((ROOT / "content" / "matches" / f"{args.name}.json").read_text(encoding="utf-8"))
    first, last = book["book_pages"]
    ocr = [dict(w, norm=normalize_word(w["text"])) for n in range(first, last + 1) for w in ocr_words(n)]
    ocr = [w for w in ocr if w["norm"]]

    mine = my_tokens(book)
    align(mine, ocr)
    db = db_words(book, matches)
    flagged, counts = [], {}
    for t in mine:
        kind = classify(t, db.get((t["entry"], t["index"])) if t["field"] == "text" else None)
        counts[kind] = counts.get(kind, 0) + 1
        if kind in ("memory", "mine", "ocr-only", "order"):
            flagged.append({"kind": kind, "entry": t["entry"], "field": t["field"], "index": t["index"],
                            "mine": t["text"], "ocr": t["ocr"]["text"], "ocr_conf": t["ocr"]["conf"],
                            "database": db.get((t["entry"], t["index"])) if t["field"] == "text" else None, "page": t["ocr"]["page"],
                            "_t": t})

    order = {"memory": 0, "mine": 1, "order": 2, "ocr-only": 3}
    flagged.sort(key=lambda f: (order[f["kind"]], f["entry"], f["index"]))
    if args.crops:
        out_dir = ROOT / ".cache" / "ocr" / "flags" / args.name
        out_dir.mkdir(parents=True, exist_ok=True)
        doc = pymupdf.open(PDF)
        for k, f in enumerate(flagged, 1):
            f["crop"] = str((out_dir / f"{k:03d}-{f['kind']}-e{f['entry']}.png").relative_to(ROOT))
            save_crop(doc, f["_t"], ocr, ROOT / f["crop"])
    for f in flagged:
        del f["_t"]
    if args.crops and flagged:
        sheets = save_sheets([ROOT / f["crop"] for f in flagged], out_dir)
        print(f"{len(flagged)} crops in {len(sheets)} sheet(s): " + ", ".join(str(s.relative_to(ROOT)) for s in sheets))

    total = len(mine)
    print(f"{total} words: " + ", ".join(f"{k} {v} ({v / total:.0%})" for k, v in sorted(counts.items())))
    for f in flagged:
        print(f"{f['kind']:<9} entry {f['entry']:>3} {f['field']:<8} p.{f['page']}  mine={f['mine']}  "
              f"ocr={f['ocr']} ({f['ocr_conf']:.0f})  db={f['database']}")
    out = ROOT / ".cache" / "reports" / f"{args.name}-ocr.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"counts": counts, "flagged": flagged}, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
