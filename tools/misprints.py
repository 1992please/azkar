"""Find the book's likely printing slips, correct the certain ones, list the rest.

Usage: python tools/misprints.py adhan [--offline]

Run tools/match.py (and tools/ocr.py for the chapter's pages) first.
Candidates are every difference between an entry and its matched hadith, and,
in entries with no match, every word that occurs nowhere in the collections.
For each one:

1. Is the printed wording attested? It is searched, with as much context as
   the alternative wording is found with (up to three words on each side), in
   all the hadith collections (tools/corpus.py) and, for the hadith text
   itself, on dorar.net (tools/dorar.py). If it occurs, it is a genuine
   variant: the book is kept and nothing is asked.
2. Typical differences between narrations and editions are kept without
   asking, as long as the printed word is a real word: a conjunction or
   preposition prefix (و ف ل ب ك), a missing or extra particle (في، من، ثم …),
   a different transmission verb (حدثنا / أخبرني …), a spelling-only
   difference (إسحاق / إسحق), or swapped word order. So is any difference
   whose alternative has no support beyond the one matched database text.
3. Otherwise a score estimates how likely the printed wording is a slip. It
   starts from the kind of difference (a slip of one or two letters in one
   word is the typical printing error; a missing, extra or reordered word is
   less certain) and is raised when the printed word exists nowhere at all,
   when the alternative is attested many times, and when the OCR confirms the
   page really prints it. If the OCR reads the alternative instead, the
   difference is probably a transcription mistake and is listed for checking
   instead.
4. A score of 0.90 or more approves the correction automatically; anything
   lower is proposed and the owner is asked.

Corrections the owner has decided are never changed. Results: corrections in
content/book/<name>.json, the full analysis in content/matches/<name>-misprints.json.
"""

import argparse
import difflib
import json
import pathlib
import re

from arabic import TASHKEEL, normalize_word, words
from book import BOOK_DIR, corrected, load_chapter
from corpus import Corpus

ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESHOLD = 0.90
MAX_WORDS = 3          # longer differences are different wordings, not slips
SALUTATION = "ﷺ"
PREFIXES = ("و", "ف", "ل", "ب", "ك", "ال")
PARTICLES = {"في", "من", "الي", "علي", "عن", "و", "ف", "ثم", "قد", "لقد", "ان", "اذا", "لو", "يا"}
NAME_BEFORE = {"بن", "ابي", "ابو", "ام", "بنت"}  # a word after these is part of a name
TRANSMISSION = {"حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "انباني", "سمعت", "عن", "قال", "ثنا"}
SALUTATION_WORDS = [normalize_word(w) for w in "صلى الله عليه وسلم".split()]


def levenshtein(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def plain(token: str) -> str:
    """A database word without tashkeel or punctuation, for writing a correction."""
    return re.sub(r"[^ء-ي]", "", TASHKEEL.sub("", token))


def tokens_with_words(text: str) -> tuple[list[str], list[str], list[int]]:
    """Tokens of the text, their normalized words, and the token each word came from."""
    toks = text.split()
    ws, owners = [], []
    for i, t in enumerate(toks):
        for w in (SALUTATION_WORDS if t == SALUTATION else [normalize_word(t)]):
            if w:
                ws.append(w)
                owners.append(i)
    return toks, ws, owners


def bold_tokens(toks: list[str]) -> set[int]:
    out, bold = set(), False
    for i, t in enumerate(toks):
        if t.startswith("**"):
            bold = True
        if bold:
            out.add(i)
        if t.endswith("**"):
            bold = False
    return out


class Evidence:
    def __init__(self, offline: bool):
        self.corpus = Corpus()
        self.offline = offline

    def counts(self, left: list[str], middle: list[str], right: list[str]) -> dict[int, int]:
        """Occurrences of the middle words with k = 3, 2, 1, 0 context words on each side."""
        out = {}
        for k in (3, 2, 1, 0):
            phrase = left[len(left) - k:] if k else []
            phrase = phrase + middle + right[:k]
            out[k] = self.corpus.count(" ".join(phrase)) if phrase else 0
        return out

    def dorar(self, left: list[str], middle: list[str], right: list[str], query_words: list[str]) -> int:
        """How many dorar.net narrations contain the middle words with two context words each side."""
        if self.offline or not query_words:
            return 0
        from dorar import search
        phrase = " ".join(left[-2:] + middle + right[:2])
        try:
            results = search(" ".join(query_words))
        except Exception as error:  # network trouble shouldn't stop the run
            print(f"  dorar.net unavailable ({error}); continuing without it")
            self.offline = True
            return 0
        return sum(f" {phrase} " in " " + " ".join(words(r["text"])) + " " for r in results)


def ocr_readings(name: str, book: dict) -> dict:
    """(entry, token index) → the OCR word read there, if the chapter has been OCR'd."""
    try:
        from ocr import words as ocr_words
        from ocr_check import align, my_tokens
        first, last = book["book_pages"]
        ocr = [dict(w, norm=normalize_word(w["text"])) for n in range(first, last + 1) for w in ocr_words(n)]
    except FileNotFoundError:
        return {}
    ocr = [w for w in ocr if w["norm"]]
    mine = my_tokens(book)
    align(mine, ocr)
    return {(t["entry"], t["index"]): t["ocr"]["norm"] for t in mine if t["field"] == "text" and t.get("ocr")}


def typical_variant(kind: str, p: list[str], a: list[str]) -> str | None:
    """A short description if the difference is a usual narration or edition variant."""
    if kind == "order":
        return "the same words in a different order"
    if kind in ("missing", "extra") and len(p + a) == 1 and (p + a)[0] in PARTICLES:
        return f"a {'missing' if kind == 'missing' else 'extra'} particle"
    if kind == "substitution":
        x, y = p[0], a[0]
        if any(x == pre + y or y == pre + x for pre in PREFIXES):
            return "a conjunction or preposition prefix"
        if x in TRANSMISSION and y in TRANSMISSION:
            return "a different transmission verb"
        if x + "ت" == y or y + "ت" == x:
            return "a masculine/feminine verb ending"
    x, y = "".join(p), "".join(a)
    if x and y and x[0] == y[0] and x[-1] == y[-1] and x[1:-1].replace("ا", "") == y[1:-1].replace("ا", ""):
        return "a spelling-only difference (a long-vowel alif written or left out)"
    return None


def score(kind: str, p: list[str], a: list[str], nonword: bool, strength: int, ocr_confirms: bool,
          in_name: bool = False, truncated: bool = False) -> float:
    if kind == "substitution":
        base = 0.80 if levenshtein(p[0], a[0]) <= 2 else 0.55
    elif kind == "missing":
        base = 0.60 if len(a) == 1 else 0.45
    elif kind == "extra":
        base = 0.55 if len(p) == 1 else 0.45
    elif kind == "order":
        base = 0.50
    else:
        base = 0.45
    if nonword:
        base += 0.10
    if strength >= 10:
        base += 0.08
    elif strength >= 3:
        base += 0.05
    elif strength <= 1:
        base -= 0.10
    if ocr_confirms:
        base += 0.03
    # Calibrated on the owner's answers for the Adhan chapter: a name spelled in a way no
    # narration uses, and a word cut short that appears in full in the same hadith, were
    # all real misprints.
    if in_name:
        base += 0.10
    if truncated:
        base += 0.05
    return round(min(base, 0.99), 2)


def unique_span(toks: list[str], i1: int, i2: int, field_text: str) -> tuple[int, int]:
    """Widen [i1, i2) with neighbouring tokens until the text it covers occurs once."""
    lo, hi = i1, i2
    while True:
        if lo < hi and field_text.count(" ".join(toks[lo:hi])) == 1:
            return lo, hi
        if lo == 0 and hi == len(toks):
            return lo, hi
        lo, hi = max(0, lo - 1), min(len(toks), hi + 1)


def candidates_for_match(entry: dict, text: str, db_text: str) -> list[dict]:
    toks, bw, b_owner = tokens_with_words(text)
    db_toks, dw, d_owner = tokens_with_words(db_text)
    out = []
    ops = [op for op in difflib.SequenceMatcher(None, bw, dw, autojunk=False).get_opcodes() if op[0] != "equal"]
    # A word missing in one place and extra a word or two later is a swap: merge the two.
    merged, k = [], 0
    while k < len(ops):
        tag, i1, i2, j1, j2 = ops[k]
        if k + 1 < len(ops):
            tag2, i3, i4, j3, j4 = ops[k + 1]
            gap = i3 - i2
            if {tag, tag2} == {"insert", "delete"} and gap <= 2 and \
                    sorted(bw[i1:i2] + bw[i3:i4]) == sorted(dw[j1:j2] + dw[j3:j4]) and bw[i1:i2] + bw[i3:i4]:
                merged.append(("order", i1, i4, j1, j4))
                k += 2
                continue
        merged.append(ops[k])
        k += 1
    for tag, i1, i2, j1, j2 in merged:
        if tag in ("insert", "delete") and (i1 == 0 or i2 == len(bw)):
            continue  # the book quotes less or more than the database text at its start or end
        p, a = bw[i1:i2], dw[j1:j2]
        if len(p) > MAX_WORDS or len(a) > MAX_WORDS:
            continue
        t1 = b_owner[i1] if i2 > i1 else b_owner[i1 - 1] + 1
        t2 = b_owner[i2 - 1] + 1 if i2 > i1 else t1
        if any(toks[t] == SALUTATION for t in range(t1, t2)):
            continue
        if not p:
            kind = "missing"
        elif not a:
            kind = "extra"
        elif tag == "order" or (sorted(p) == sorted(a) and len(p) > 1):
            kind = "order"
        elif len(p) == len(a) == 1:
            kind = "substitution"
        else:
            kind = "other"
        out.append({"entry": entry["number"], "kind": kind, "tokens": (t1, t2),
                    "printed_words": p, "alternative_words": a,
                    "alternative_tokens": [plain(db_toks[d_owner[j]]) for j in range(j1, j2)
                                           if j == j1 or d_owner[j] != d_owner[j - 1]],
                    "left": bw[max(0, i1 - 3):i1], "right": bw[i2:i2 + 3]})
    return out


def candidates_for_unmatched(entry: dict, text: str, corpus: Corpus) -> list[dict]:
    toks, bw, b_owner = tokens_with_words(text)
    out = []
    for i, w in enumerate(bw):
        if corpus.freq(w) or toks[b_owner[i]] == SALUTATION:
            continue
        left, right = bw[max(0, i - 2):i], bw[i + 1:i + 3]
        found = {}
        for before, after in ((left, right[:1]), (left[-1:], right[:1]), (left, []), ([], right)):
            if before or after:
                for alt, n in corpus.fill(before, after).items():
                    if levenshtein(alt, w) <= 2:
                        found[alt] = max(found.get(alt, 0), n)
        t = b_owner[i]
        cand = {"entry": entry["number"], "kind": "substitution" if found else "unknown",
                "tokens": (t, t + 1), "printed_words": [w], "left": left, "right": right}
        if found:
            alt = max(found, key=lambda x: (found[x], -levenshtein(x, w)))
            cand.update(alternative_words=[alt], alternative_tokens=[alt])
        else:
            cand.update(alternative_words=[], alternative_tokens=[])
        out.append(cand)
    return out


def evaluate(c: dict, ev: Evidence, toks: list[str], bold: set[int], ocr: dict, entry_words: list[str]) -> None:
    p, a, left, right = c["printed_words"], c["alternative_words"], c["left"], c["right"]
    t1, t2 = c["tokens"]
    c["nonword"] = any(ev.corpus.freq(w) == 0 for w in p)
    if c["kind"] == "unknown":
        c.update(decision="unknown", confidence=None,
                 evidence="The printed word occurs nowhere in the collections, and no similar word was found in this context.")
        return
    count_p, count_a = ev.counts(left, p, right), ev.counts(left, a, right)
    k = next((k for k in (3, 2, 1) if count_a[k] >= 1), None)
    printed_attested = count_p[k] if k else count_p[1]
    in_hadith_text = bool(set(range(t1, max(t2, t1 + 1))) & bold)
    query_context = lambda mid: left[-3:] + mid + right[:3]
    dorar_p = dorar_a = 0
    if in_hadith_text and not printed_attested:
        dorar_p = ev.dorar(left, p, right, query_context(p))
        dorar_a = ev.dorar(left, a, right, query_context(a))
    # How well the alternative is attested, at the shortest context where the printed wording occurs nowhere.
    unattested = [j for j in (1, 2, 3) if count_p[j] == 0 and (k is None or j <= k)]
    strength = (count_a[unattested[0]] if unattested else 0) + dorar_a
    # A printed word that is a cut-off form of a word used in full elsewhere in the same entry
    # (e.g. a word quoted twice) is evidence for the full form.
    truncated = len(p) == len(a) == 1 and (a[0].startswith(p[0]) or a[0].endswith(p[0]))
    internal = sum(1 for w in entry_words if w == a[0]) if truncated else 0
    strength += 2 * internal
    read = [ocr.get((c["entry"], t)) for t in range(t1, t2)]
    ocr_confirms = bool(p) and all(r is not None for r in read) and \
        [w for r in read for w in [r]] == [normalize_word(toks[t]) for t in range(t1, t2)]
    ocr_reads_alternative = bool(p) and all(r is not None for r in read) and [r for r in read] == a
    c["evidence_counts"] = {"printed_in_collections": printed_attested, "context_words": k or 1,
                            "alternative_in_collections": count_a[k] if k else 0,
                            "printed_on_dorar": dorar_p, "alternative_on_dorar": dorar_a,
                            "ocr_confirms_printed": ocr_confirms}
    if printed_attested or dorar_p:
        c.update(decision="variant", confidence=0.05,
                 evidence=f"The printed wording is attested elsewhere ({printed_attested} in the collections, "
                          f"{dorar_p} on dorar.net), so it is a genuine variant.")
        return
    if ocr_reads_alternative:
        c.update(decision="check-scan", confidence=None,
                 evidence="The OCR reads the alternative here: re-check the transcription on the scan.")
        return
    variant = typical_variant(c["kind"], p, a)
    if not c["nonword"] and variant:
        c.update(decision="kept", confidence=0.15,
                 evidence=f"Kept: {variant}, a usual difference between narrations and editions.")
        return
    if not c["nonword"] and strength <= 1:
        c.update(decision="kept", confidence=0.15,
                 evidence="Kept: the alternative has no support beyond the one matched database text.")
        return
    # A name: anywhere in the chain of narrators (regular type), or after أبي / بن … in the hadith text.
    in_name = c["kind"] == "substitution" and (not in_hadith_text or (left and left[-1] in NAME_BEFORE))
    conf = score(c["kind"], p, a, c["nonword"], strength, ocr_confirms, in_name, bool(internal))
    parts = [f"the printed wording occurs nowhere ({'with ' + str(k) + ' word(s) of context' if k else 'in context'})"]
    if c["nonword"]:
        parts.append("the printed word exists nowhere in the collections")
    parts.append(f"the alternative is attested {count_a[k] if k else 0} time(s) in the collections"
                 + (f" and {dorar_a} on dorar.net" if in_hadith_text and not ev.offline else ""))
    if in_name:
        parts.append("it is part of a name, and the printed spelling is used in no narration")
    if internal:
        parts.append("the alternative also appears elsewhere in this entry")
    if ocr_confirms:
        parts.append("the OCR confirms the page prints it")
    c.update(decision="approve" if conf >= THRESHOLD else "ask", confidence=conf,
             evidence=f"{c['kind'].capitalize()}: " + "; ".join(parts) + ".")


def correction_strings(c: dict, toks: list[str], text: str) -> tuple[str, str]:
    t1, t2 = c["tokens"]
    lo, hi = unique_span(toks, t1, t2, text)
    if lo == t1 == t2 == hi:  # a missing word with nothing around it can't happen inside an entry
        lo, hi = max(0, t1 - 1), min(len(toks), t1 + 1)
    if c["kind"] == "missing" and lo == t1 and hi == t2:
        lo, hi = max(0, t1 - 1), min(len(toks), t2 + 1)
    printed = " ".join(toks[lo:hi])
    new_middle = c["alternative_tokens"]
    # keep bold markers that sat on the replaced tokens
    old_middle = toks[t1:t2]
    if old_middle and new_middle:
        if old_middle[0].startswith("**"):
            new_middle = ["**" + new_middle[0]] + new_middle[1:]
        if old_middle[-1].endswith("**"):
            new_middle = new_middle[:-1] + [new_middle[-1] + "**"]
    fixed = toks[lo:t1] + new_middle + toks[t2:hi]
    return printed, " ".join(fixed)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--offline", action="store_true", help="don't query dorar.net")
    args = parser.parse_args()

    book = load_chapter(args.name)
    matches = {r["number"]: r for r in json.loads(
        (ROOT / "content" / "matches" / f"{args.name}.json").read_text(encoding="utf-8"))["results"]}
    ev = Evidence(args.offline)
    ocr = ocr_readings(args.name, book)
    analysis = []

    # Numbers already given to corrections stay the same from run to run.
    previous = {(c["field"], c["printed"], c["corrected"]): c["id"]
                for e in book["entries"] for c in e["corrections"] if c.get("id")}
    for e in book["entries"]:
        # Kept as they are: the owner's decisions, and corrections proposed by hand.
        owner = [c for c in e["corrections"] if c.get("decided_by") == "owner" or c.get("source") == "transcriber"]
        settled = dict(e, corrections=owner)
        text = corrected(settled, "text")
        toks = text.split()
        bold = bold_tokens(toks)
        m = matches[e["number"]]["match"]
        cands = candidates_for_match(e, text, m["text"]) if m else candidates_for_unmatched(e, text, ev.corpus)
        new = []
        entry_words = words(text)
        for c in cands:
            evaluate(c, ev, toks, bold, ocr, entry_words)
            if c["decision"] in ("approve", "ask"):
                c["printed"], c["corrected"] = correction_strings(c, toks, text)
                if any(o["field"] == "text" and (c["printed"] in o["printed"] or o["printed"] in c["printed"])
                       for o in owner):
                    c["decision"] = "owner-decided"
                else:
                    new.append(c)
            analysis.append(dict(c))
        e["corrections"] = owner
        for c in new:
            e["corrections"].append({
                "id": None, "field": "text", "printed": c["printed"], "corrected": c["corrected"],
                "confidence": c["confidence"], "status": "approved" if c["decision"] == "approve" else "proposed",
                "decided_by": "auto" if c["decision"] == "approve" else None, "reason": c["evidence"]})

    # Number the corrections after the owner's, in entry order; one id per distinct correction.
    ids = {}
    next_id = 1 + max(list(previous.values()) or [0])
    for e in book["entries"]:
        for c in e["corrections"]:
            if c["id"] is None:
                key = (c["field"], c["printed"], c["corrected"])
                if key in previous:
                    ids[key] = previous[key]
                if key not in ids:
                    ids[key], next_id = next_id, next_id + 1
                c["id"] = ids[key]
    (BOOK_DIR / f"{args.name}.json").write_text(json.dumps(book, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    out = ROOT / "content" / "matches" / f"{args.name}-misprints.json"
    out.write_text(json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {}
    for c in analysis:
        summary[c["decision"]] = summary.get(c["decision"], 0) + 1
    print(f"{len(analysis)} candidates: " + ", ".join(f"{k} {v}" for k, v in sorted(summary.items())))
    for c in analysis:
        conf = f"{c['confidence']:.2f}" if c["confidence"] is not None else "  - "
        print(f"{c['decision']:<13} {conf}  entry {c['entry']:>3}  {c['kind']:<12} "
              f"{' '.join(c['printed_words']) or '∅'} → {' '.join(c['alternative_words']) or '∅'}  "
              f"{c.get('evidence_counts', '')}")


if __name__ == "__main__":
    main()
