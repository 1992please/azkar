"""Match transcribed book entries to vocalized hadith.

Usage: python tools/match.py content/book/adhan.json

Writes content/matches/<same name>.json. Run tools/fetch_hadith.py first.

Each entry's text is compared with every hadith by word pairs:
- containment: share of the book's word pairs found in the hadith
- coverage:    share of the hadith's word pairs found in the book's text
Containment decides the match; coverage shows when the database hadith
holds much more than the book quotes (e.g. extra chains of narrators).

The cited collection is searched in hadith-api first (standard numbering).
Open-Hadith-Data is used only when hadith-api has no match, which covers
hadith-api's gaps and the collections it lacks (Ahmad, al-Darimi).
"""

import argparse
import csv
import json
import pathlib

from arabic import words
from fetch_hadith import (HADITH_API_COLLECTIONS, OPEN_HADITH_FILES,
                          hadith_api_path, open_hadith_path)

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "content" / "matches"
# Collections whose standard numbers sunnah.com links use.
SUNNAH_LINKS = {"bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah"}

MATCHED = 0.75
POSSIBLE = 0.40
SAME_TEXT = 0.95  # word-pair overlap above which two hadith count as the same text


def pairs(ws: list[str]) -> set[tuple[str, str]]:
    return set(zip(ws, ws[1:]))


def load_hadith_api() -> list[dict]:
    rows = []
    for name in HADITH_API_COLLECTIONS:
        data = json.loads(hadith_api_path(name).read_text(encoding="utf-8"))
        sections = data["metadata"]["sections"]
        for h in data["hadiths"]:
            p = pairs(words(h["text"]))
            if not p:
                continue
            # arabicnumber is the standard numbering (Fuad Abd al-Baqi for
            # Muslim); sub-narrations look like "447.01".
            number = str(h.get("arabicnumber", h["hadithnumber"])).removesuffix(".0")
            url = None
            if name in SUNNAH_LINKS:
                url = f"https://sunnah.com/{name}:{number.split('.')[0]}"
            rows.append({
                "source": "hadith-api", "collection": name, "number": number,
                "kitab": sections.get(str(h["reference"]["book"])),
                "url": url, "text": h["text"], "pairs": p,
            })
    return rows


def load_open_hadith() -> list[dict]:
    csv.field_size_limit(10**8)
    rows = []
    for name in OPEN_HADITH_FILES:
        with open_hadith_path(name).open(encoding="utf-8", newline="") as f:
            for record in csv.reader(f):
                text = " ".join(record[1].replace("‏", " ").split())
                p = pairs(words(text))
                if p:
                    rows.append({
                        "source": "open-hadith-data", "collection": name, "number": record[0],
                        "kitab": None, "url": None, "text": text, "pairs": p,
                    })
    return rows


def rank(entry_pairs: set, rows: list[dict]) -> list[dict]:
    scored = []
    for row in rows:
        common = len(entry_pairs & row["pairs"])
        if common:
            scored.append({**row,
                           "containment": round(common / len(entry_pairs), 2),
                           "coverage": round(common / len(row["pairs"]), 2)})
    scored.sort(key=lambda c: (c["containment"], c["coverage"]), reverse=True)
    return scored[:5]


def same_text(a: dict, b: dict) -> bool:
    return len(a["pairs"] & b["pairs"]) / len(a["pairs"] | b["pairs"]) >= SAME_TEXT


def decide(ranked: list[dict]) -> tuple[str, dict | None, list[dict]]:
    """Return (status, best match, other hadith with the same text)."""
    if not ranked or ranked[0]["containment"] < POSSIBLE:
        return "not_found", None, []
    best, rest = ranked[0], ranked[1:]
    duplicates = [c for c in rest if same_text(best, c)]
    close = [c for c in rest if c not in duplicates and c["containment"] >= best["containment"] - 0.05]
    if best["containment"] < MATCHED:
        return "check", best, duplicates
    if close:
        return "ambiguous", best, duplicates
    return "matched", best, duplicates


def public(c: dict | None) -> dict | None:
    return None if c is None else {k: v for k, v in c.items() if k != "pairs"}


def label(c: dict) -> str:
    return f"{c['collection']} {c['number']}" + (" (open-hadith-data)" if c["source"] == "open-hadith-data" else "")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("book_file", type=pathlib.Path)
    args = parser.parse_args()

    book = json.loads(args.book_file.read_text(encoding="utf-8"))
    api_rows, open_rows = load_hadith_api(), load_open_hadith()
    known = set(HADITH_API_COLLECTIONS) | set(OPEN_HADITH_FILES)
    # For "found elsewhere": hadith-api, plus Open-Hadith-Data only for the
    # collections hadith-api lacks, so the same hadith isn't listed twice.
    elsewhere_rows = api_rows + [r for r in open_rows if r["collection"] not in HADITH_API_COLLECTIONS]

    results = []
    for entry in book["entries"]:
        entry_pairs = pairs(words(entry["text"]))
        cited = entry["source"]["collection"]
        if cited in known:
            ranked = rank(entry_pairs, [r for r in api_rows if r["collection"] == cited])
            status, best, duplicates = decide(ranked)
            if status != "matched":
                fallback = rank(entry_pairs, [r for r in open_rows if r["collection"] == cited])
                if fallback and (best is None or fallback[0]["containment"] > best["containment"]):
                    ranked = fallback
                    status, best, duplicates = decide(ranked)
        else:
            ranked, status, best, duplicates = [], "not_in_dataset", None, []
        alternatives = [c for c in ranked if c is not best and c not in duplicates][:2]
        elsewhere = rank(entry_pairs, [r for r in elsewhere_rows if r["collection"] != cited])[:3]
        results.append({
            "number": entry["number"],
            "cited_collection": cited,
            "status": status,
            "match": public(best),
            "same_text_also_at": [label(c) for c in duplicates],
            "alternatives": [public(c) for c in alternatives],
            "other_collections": [public(c) for c in elsewhere],
            "review": {"confirmed": None, "note": None},
        })
        shown = f"{label(best)} ({best['containment']:.0%})" if best else "-"
        print(f"{entry['number']:>4}  {status:<15} {shown}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / args.book_file.name
    out.write_text(json.dumps({"chapter": book["chapter"], "results": results},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
