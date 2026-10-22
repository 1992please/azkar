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
   a different transmission verb (حدثنا / أخبرني …, or the abbreviation ثنا),
   a spelling-only difference (إسحاق / إسحق, طاووس / طاوس, ألا / أن لا), or swapped word
   order. So is any difference whose alternative has no support beyond the one
   matched database text. Transmission verbs and spelling-only differences are
   kept even when the printed form occurs in no collection.
   The hadith text is the exception (the owner's decision of 2026-10-15): when
   the entry is matched, unambiguously and at least 90%, in the collection the
   book cites, any other difference strictly inside the hadith text is corrected
   to the cited source's wording, whatever its score and the always-asked cases
   of step 4. Not at the hadith text's start or end, nor next to a quotation
   mark, Quran bracket, bracket or dash: there the book may have shortened the
   hadith or added an aside on purpose.
3. Otherwise a score estimates how likely the printed wording is a slip. It
   starts from the kind of difference (a slip of one or two letters in one
   word is the typical printing error; a missing, extra or reordered word is
   less certain) and is raised when the printed word exists nowhere at all,
   when the alternative is attested many times, and when the OCR confirms the
   page really prints it. If the OCR reads the alternative instead, the
   difference is probably a transcription mistake and is listed for checking
   instead.
4. A score of 0.90 or more approves the correction automatically; anything
   lower is proposed and the owner is asked. Some corrections are always asked,
   whatever their score: when the alternative is attested nowhere in this
   context, when the entry has no matched hadith (its source isn't in the
   databases, so its chain can't be compared), and when the difference is an
   attached pronoun added or dropped (either form can be grammatical).

If dorar.net can't be reached (a request fails twice), the run goes on without it, and the
candidates it would have been searched for are marked `dorar_skipped`: their decisions may change
once it can be searched, so the review page says so.

Corrections the owner has decided are never changed. Results: corrections in
content/book/<name>.json, the full analysis in content/matches/<name>-misprints.json.
"""

import argparse
import difflib
import json
import pathlib
import re
import time

from arabic import TASHKEEL, normalize_word, words
from book import BOOK_DIR, corrected, load_chapter
from corpus import Corpus

ROOT = pathlib.Path(__file__).resolve().parent.parent
THRESHOLD = 0.90
MAX_WORDS = 3          # longer differences are different wordings, not slips
SALUTATION = "ﷺ"
PREFIXES = ("و", "ف", "ل", "ب", "ك", "ال")
PRONOUN_SUFFIXES = ("ه", "ها", "هم", "هما", "هن", "ك", "كم", "ني", "نا")
PARTICLES = {"في", "من", "الي", "علي", "عن", "و", "ف", "ثم", "قد", "لقد", "ان", "اذا", "لو", "يا"}
NAME_BEFORE = {"بن", "ابي", "ابو", "ام", "بنت"}  # a word after these is part of a name
TRANSMISSION = {"حدثنا", "حدثني", "اخبرنا", "اخبرني", "انبانا", "انباني", "سمعت", "عن", "قال", "ثنا"}
SALUTATION_WORDS = [normalize_word(w) for w in "صلى الله عليه وسلم".split()]
ASK_CAP = 0.85  # the highest score of a correction that is always asked
CITED_MATCH = 0.90  # the cited source's wording wins only in entries matched at least this closely
EDGE_MARKS = ("«", "»", "﴿", "﴾", "**", "(", ")", "[", "]", "-")
DORAR_RETRY = 10  # seconds to wait before trying a failed dorar.net request again


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


def neighbours(cands: list[dict]) -> list[list[dict]]:
    """The candidates grouped into changes: those at most two tokens apart go together."""
    groups = []
    for c in sorted(cands, key=lambda c: c["tokens"]):
        if groups and c["tokens"][0] - groups[-1][-1]["tokens"][1] <= 2:
            groups[-1].append(c)
        else:
            groups.append([c])
    return groups


def inside_hadith_text(toks: list[str], bold: set[int], t1: int, t2: int) -> bool:
    """The tokens t1..t2 (empty for a missing word) lie strictly inside the hadith text: bold on both
    sides, and no quotation mark, Quran bracket, bracket or dash on or next to them. At those edges
    the book may have shortened the hadith or added an aside, and a missing word's place is unsure
    (the database marks neither quotations nor Quran verses)."""
    if t1 < 1 or t2 >= len(toks) or t1 - 1 not in bold or t2 not in bold:
        return False
    return not any(mark in toks[t] for t in range(t1 - 1, t2 + 1) for mark in EDGE_MARKS)


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

    def dorar(self, left: list[str], middle: list[str], right: list[str], query_words: list[str]) -> int | None:
        """How many dorar.net narrations contain the middle words with two context words each side,
        or None if dorar.net isn't searched (--offline, or it can't be reached)."""
        if self.offline:
            return None
        if not query_words:
            return 0
        from dorar import search
        phrase = " ".join(left[-2:] + middle + right[:2])
        for attempt in (1, 2):
            try:
                results = search(" ".join(query_words))
                break
            except Exception as error:  # network trouble shouldn't stop the run
                if attempt == 2:
                    print(f"  dorar.net unavailable ({error}); continuing without it")
                    self.offline = True
                    return None
                time.sleep(DORAR_RETRY)
        return sum(f" {phrase} " in " " + " ".join(words(r["text"])) + " " for r in results)


def ocr_readings(name: str, book: dict) -> dict:
    """(entry, token index) → the OCR word read there, if the chapter has been OCR'd."""
    try:
        from ocr import main_words
        from ocr_check import align, my_tokens
        first, last = book["book_pages"]
        ocr = [dict(w, norm=normalize_word(w["text"])) for n in range(first, last + 1) for w in main_words(n)]
    except FileNotFoundError:
        return {}
    ocr = [w for w in ocr if w["norm"]]
    mine = my_tokens(book)
    align(mine, ocr)
    return {(t["entry"], t["index"]): t["ocr"]["norm"] for t in mine if t["field"] == "text" and t.get("ocr")}


def transmission(w: str) -> bool:
    """A transmission word, with or without a conjunction prefix (وحدثنا, فقال)."""
    return w in TRANSMISSION or (w[:1] in ("و", "ف") and w[1:] in TRANSMISSION)


def joined(ws: list[str]) -> str:
    """The words written as one; «أن لا» is written joined as «ألا», its nun assimilated."""
    return re.sub(r"(?<!\S)ان لا(?!\S)", "الا", " ".join(ws)).replace(" ", "")


def form_variant(kind: str, p: list[str], a: list[str]) -> str | None:
    """A short description if both sides are the same word written differently.

    These are kept even when the printed form occurs in no collection: the corpus has
    one edition's spelling, and the chain's abbreviations (ثنا) are rarely in it."""
    if kind == "substitution" and transmission(p[0]) and transmission(a[0]):
        return "a different transmission verb"
    x, y = joined(p), joined(a)
    middle = lambda w: w[1:-1].replace("ا", "").replace("وو", "و")
    if x and y and x[0] == y[0] and x[-1] == y[-1] and middle(x) == middle(y):
        return "a spelling-only difference (a long-vowel alif or a doubled waw, or words written joined)"
    return None


def pronoun_suffix(kind: str, p: list[str], a: list[str]) -> bool:
    """One side is the other with an attached pronoun (تطحنه / تطحن, يراني / يرى)."""
    if kind != "substitution":
        return False
    x, y = p[0], a[0]
    return any(x in {stem + s for stem in stems(y)} or y in {stem + s for stem in stems(x)}
               for s in PRONOUN_SUFFIXES)


def stems(w: str) -> set[str]:
    """A normalized word as written before an attached pronoun: a final ى (normalized ي) turns
    into ا (يرى / يراني) and a final ة (normalized ه) into ت (صلاة / صلاته)."""
    out = {w}
    if w.endswith("ي"):
        out.add(w[:-1] + "ا")
    if w.endswith("ه"):
        out.add(w[:-1] + "ت")
    return out


def typical_variant(kind: str, p: list[str], a: list[str]) -> str | None:
    """A short description if the difference is a usual narration variant (form_variant is checked first)."""
    if kind == "order":
        return "the same words in a different order"
    if kind in ("missing", "extra") and len(p + a) == 1 and (p + a)[0] in PARTICLES:
        return f"a {'missing' if kind == 'missing' else 'extra'} particle"
    if kind == "substitution":
        x, y = p[0], a[0]
        if any(x == pre + y or y == pre + x for pre in PREFIXES):
            return "a conjunction or preposition prefix"
        if x + "ت" == y or y + "ت" == x:
            return "a masculine/feminine verb ending"
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


def evaluate(c: dict, ev: Evidence, toks: list[str], bold: set[int], ocr: dict, entry_words: list[str],
             matched: bool = True, source: str | None = None) -> None:
    """Decide one candidate. source names the matched hadith (e.g. "bukhari 843") when the entry is
    matched, unambiguously, in the collection the book cites."""
    c["cited_wins"] = False
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
        if dorar_p is None or dorar_a is None:
            c["dorar_skipped"] = True
            dorar_p, dorar_a = dorar_p or 0, dorar_a or 0
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
    form = form_variant(c["kind"], p, a)
    if form:
        c.update(decision="kept", confidence=0.15,
                 evidence=f"Kept: {form}, a usual difference between editions.")
        return
    # The owner's decision (2026-10-15): in the hadith text of an entry matched in the collection the book
    # cites, the cited source's wording is used. The book's wording is attested in no narration (checked
    # above), so it is most likely a printing slip. Not when dorar.net couldn't be searched, as it might
    # attest the book's wording. The chain of narrators keeps the rules below: the book shortens chains.
    cited_wins = bool(source) and inside_hadith_text(toks, bold, t1, t2) and not c.get("dorar_skipped") and strength > 0
    variant = typical_variant(c["kind"], p, a)
    if not c["nonword"] and variant and not cited_wins:
        c.update(decision="kept", confidence=0.15,
                 evidence=f"Kept: {variant}, a usual difference between narrations and editions.")
        return
    if not c["nonword"] and strength <= 1 and not cited_wins:
        c.update(decision="kept", confidence=0.15,
                 evidence="Kept: the alternative has no support beyond the one matched database text.")
        return
    # A name: anywhere in the chain of narrators (regular type), or after أبي / بن … in the hadith text.
    in_name = c["kind"] == "substitution" and not transmission(p[0]) and not transmission(a[0]) and \
        (not in_hadith_text or (left and left[-1] in NAME_BEFORE))
    conf = score(c["kind"], p, a, c["nonword"], strength, ocr_confirms, in_name, bool(internal))
    # Always asked, whatever the score (except where the cited source's wording is used).
    always_ask = []
    if strength == 0:
        always_ask.append("the alternative is attested nowhere in this context")
    if not matched:
        always_ask.append("the entry's source isn't in the databases, so its wording can't be compared")
    if pronoun_suffix(c["kind"], p, a) and not in_name:  # a name's ة is normalized to ه
        always_ask.append("an attached pronoun is added or dropped, and either form can be grammatical")
    if cited_wins:
        always_ask = []
        conf = max(conf, THRESHOLD)
    elif always_ask:
        conf = min(conf, ASK_CAP)
    parts = [f"the printed wording occurs nowhere ({'with ' + str(k) + ' word(s) of context' if k else 'in context'})"]
    if c["nonword"]:
        parts.append("the printed word exists nowhere in the collections")
    parts.append(f"the alternative is attested {count_a[k] if k else 0} time(s) in the collections"
                 + (f" and {dorar_a} on dorar.net" if in_hadith_text and not c.get("dorar_skipped") else ""))
    if c.get("dorar_skipped"):
        parts.append("dorar.net couldn't be searched")
    if in_name:
        parts.append("it is part of a name, and the printed spelling is used in no narration")
    if internal:
        parts.append("the alternative also appears elsewhere in this entry")
    if ocr_confirms:
        parts.append("the OCR confirms the page prints it")
    if always_ask:
        parts.append("asked rather than corrected automatically, because " + " and ".join(always_ask))
    if cited_wins:
        parts.append(f"in the hadith text the wording of the cited source ({source}) is used")
    c["cited_wins"] = cited_wins
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
        entry_words = words(text)
        # How closely the matched hadith covers the text without this tool's own corrections (the
        # match file's containment is measured with them, so it would justify them in a circle).
        own_pairs, db_words = set(zip(entry_words, entry_words[1:])), words(m["text"]) if m else []
        containment = len(own_pairs & set(zip(db_words, db_words[1:]))) / len(own_pairs) if m and own_pairs else 0
        source = f"{m['collection']} {m['number']}" if m and matches[e["number"]]["status"] == "matched" \
            and containment >= CITED_MATCH else None
        cands = candidates_for_match(e, text, m["text"]) if m else candidates_for_unmatched(e, text, ev.corpus)
        new = []
        for c in cands:
            evaluate(c, ev, toks, bold, ocr, entry_words, matched=bool(m), source=source)
        # Differences at most two words apart are one change. The cited source's wording is used only
        # if it decided every part: applied to part of a change, it would leave a wording that is in
        # neither the book nor the source (e.g. «لك الحمد ربنا» → «لك الحمد لله ربنا»).
        for group in neighbours(cands):
            if any(c.get("cited_wins") for c in group) and not all(c.get("cited_wins") for c in group):
                for c in group:
                    if c.get("cited_wins"):
                        evaluate(c, ev, toks, bold, ocr, entry_words, matched=bool(m), source=None)
        for c in cands:
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
    # Ids of corrections on the Sheikh's own text (proposed by hand) are taken too.
    ids = {}
    taken = list(previous.values()) + [c["id"] for b in book.get("author_text", [])
                                       for c in b.get("corrections", []) if c.get("id")]
    next_id = 1 + max(taken or [0])
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
    skipped = sum(1 for c in analysis if c.get("dorar_skipped"))
    if skipped:
        print(f"dorar.net wasn't searched for {skipped} candidate(s), so their decisions may change: "
              "rerun the pipeline when it can be reached.")


if __name__ == "__main__":
    main()
