"""Add tashkeel to the book's text from each entry's matched hadith.

Usage: python tools/vocalize.py adhan

Reads content/book/<name>.json and content/matches/<name>.json, writes
content/vocalized/<name>.json. Run tools/match.py first.

Rules (see "Content pipeline" in the README):
- The book's wording and letters are kept; only marks are added.
- A word takes the database's marks only when it lines up with the same word
  in the matched hadith and has the same letters.
- The book's own printed marks always stay. If the database disagrees with
  one of them, the word keeps only the book's marks and is flagged.
- Words without such a match get no tashkeel.
- Words next to a difference are flagged, because their endings can depend on it.
"""

import argparse
import difflib
import json
import pathlib

from arabic import normalize_word
from book import corrected, load_chapter

ROOT = pathlib.Path(__file__).resolve().parent.parent
MATCHES_DIR = ROOT / "content" / "matches"
OUT_DIR = ROOT / "content" / "vocalized"

MARKS = ({chr(c) for c in range(0x064B, 0x0660)} | {"ٰ"}
         | {chr(c) for c in range(0x0610, 0x061B)} | {chr(c) for c in range(0x06D6, 0x06EE)})
# Letter forms that count as the same letter when lining up a word.
FOLD = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي"})
SALUTATION = "ﷺ"
SALUTATION_WORDS = [normalize_word(w) for w in "صلى الله عليه وسلم".split()]


def is_letter(ch: str) -> bool:
    return ("ء" <= ch <= "ي" and ch != "ـ") or ch == "ٱ"


def letters(token: str) -> list[list[str]]:
    """[letter, marks] pairs for each Arabic letter of a token."""
    out = []
    for ch in token:
        if ch in MARKS:
            if out:
                out[-1][1] += ch
        elif is_letter(ch):
            out.append([ch, ""])
    return out


def transfer(book_token: str, db_token: str) -> tuple[str, str | None]:
    """Put db_token's marks on book_token's letters. Returns (token, problem)."""
    b, d = letters(book_token), letters(db_token)
    # A name that wraps to the start of a printed line is written «ابن» for «بن».
    if len(b) == len(d) + 1 and b[0][0] == "ا" and d and d[0][0] == "ب":
        d = [["ا", ""]] + d
    if len(b) != len(d) or any(x.translate(FOLD) != y.translate(FOLD) for (x, _), (y, _) in zip(b, d)):
        return book_token, "letters_differ"
    marks = []
    for (_, book_marks), (_, db_marks) in zip(b, d):
        if book_marks and db_marks and not set(book_marks) <= set(db_marks):
            return book_token, "conflict"
        marks.append(db_marks or book_marks)
    out, k = [], 0
    for ch in book_token:
        if ch in MARKS:
            continue
        out.append(ch)
        if is_letter(ch):
            out.append(marks[k])
            k += 1
    return "".join(out), None


def token_words(tokens: list[str]) -> tuple[list[str], list[int]]:
    """Normalized words of the tokens, and the token each word came from."""
    ws, owners = [], []
    for i, t in enumerate(tokens):
        parts = SALUTATION_WORDS if t == SALUTATION else [normalize_word(t)]
        for w in parts:
            if w:
                ws.append(w)
                owners.append(i)
    return ws, owners


def vocalize(text: str, db_text: str | None) -> list[dict]:
    tokens = text.split()
    has_letters = [bool(letters(t)) and t != SALUTATION for t in tokens]
    paired, near = {}, set()
    if db_text:
        db_tokens = db_text.split()
        bw, b_owner = token_words(tokens)
        dw, d_owner = token_words(db_tokens)
        matcher = difflib.SequenceMatcher(None, bw, dw, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                for k in range(i2 - i1):
                    paired.setdefault(b_owner[i1 + k], db_tokens[d_owner[j1 + k]])
                continue
            if i1 > 0:
                near.add(b_owner[i1 - 1])
            if i2 < len(bw):
                near.add(b_owner[i2])

    words = []
    for i, t in enumerate(tokens):
        if not has_letters[i]:
            words.append({"text": t, "tashkeel": None, "flag": None})
            continue
        own_marks = any(ch in MARKS for ch in t)
        if i in paired:
            new, problem = transfer(t, paired[i])
            if problem is None:
                words.append({"text": new, "tashkeel": "database",
                              "flag": "near_difference" if i in near else None})
                continue
            words.append({"text": t, "tashkeel": "book" if own_marks else "none", "flag": problem})
            continue
        words.append({"text": t, "tashkeel": "book" if own_marks else "none",
                      "flag": "no_match" if db_text else None})
    return words


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()

    book = load_chapter(args.name)
    matches = json.loads((MATCHES_DIR / f"{args.name}.json").read_text(encoding="utf-8"))
    results = {r["number"]: r for r in matches["results"]}
    entries = []
    for entry in book["entries"]:
        match = results[entry["number"]]["match"]
        words = vocalize(corrected(entry, "text"), match["text"] if match else None)
        counts = {}
        for w in words:
            if w["tashkeel"]:
                counts[w["tashkeel"]] = counts.get(w["tashkeel"], 0) + 1
            if w["flag"]:
                counts[w["flag"]] = counts.get(w["flag"], 0) + 1
        entries.append({
            "number": entry["number"],
            "heading": corrected(entry, "heading"),
            "match": f"{match['collection']} {match['number']}" if match else None,
            "text": " ".join(w["text"] for w in words),
            "counts": counts,
            "words": words,
        })
        print(f"{entry['number']:>4}  " + "  ".join(f"{k}={v}" for k, v in sorted(counts.items())))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}.json"
    out.write_text(json.dumps({"chapter": book["chapter"], "entries": entries},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
