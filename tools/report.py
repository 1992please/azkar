"""Build the HTML review page for one chapter.

Usage: python tools/report.py adhan

Reads content/book, content/matches and content/vocalized for the chapter and
writes .cache/reports/<name>.html. Run tools/match.py and tools/vocalize.py first.
"""

import argparse
import difflib
import html
import json
import pathlib
import re
import urllib.parse

from arabic import TASHKEEL, expand_salutation, normalize_word
from book import corrected, load_chapter

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / ".cache" / "reports"

COLLECTION_NAMES = {
    "bukhari": "Sahih al-Bukhari", "muslim": "Sahih Muslim", "abudawud": "Sunan Abi Dawud",
    "tirmidhi": "Jami' at-Tirmidhi", "nasai": "Sunan an-Nasa'i", "ibnmajah": "Sunan Ibn Majah",
    "malik": "Muwatta Malik", "ahmad": "Musnad Ahmad", "darimi": "Sunan ad-Darimi",
    "ibnhibban": "Sahih Ibn Hibban", "abuawana": "Mustakhraj Abi 'Awana",
}
STATUS_TEXT = {
    "matched": "Matched",
    "ambiguous": "Matched, close alternatives",
    "check": "Partial match",
    "not_found": "Not found",
    "not_in_dataset": "Book not in databases",
}
WORD_CLASS = {"near_difference": "near", "no_match": "none", "conflict": "bad", "letters_differ": "bad"}


def esc(s: str) -> str:
    return html.escape(s)


def ar(s: str, tag: str = "span") -> str:
    return f'<{tag} class="ar" lang="ar" dir="rtl">{esc(s)}</{tag}>'


def diff(book_text: str, db_text: str) -> tuple[str, str]:
    """Both texts as HTML with differing words wrapped in <mark>."""
    a = [(w, normalize_word(w)) for w in expand_salutation(book_text.replace("**", "")).split()]
    b = [(w, normalize_word(w)) for w in db_text.split()]
    ai = [i for i, (_, n) in enumerate(a) if n]
    bi = [i for i, (_, n) in enumerate(b) if n]
    matcher = difflib.SequenceMatcher(None, [a[i][1] for i in ai], [b[i][1] for i in bi], autojunk=False)
    a_marked, b_marked = set(), set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            a_marked.update(ai[i1:i2])
            b_marked.update(bi[j1:j2])

    def render(tokens, marked):
        return " ".join(f"<mark>{esc(w)}</mark>" if i in marked else esc(w) for i, (w, _) in enumerate(tokens))
    return render(a, a_marked), render(b, b_marked)


def ref(c: dict) -> str:
    name = COLLECTION_NAMES.get(c["collection"], c["collection"])
    if c["source"] == "open-hadith-data":
        return f"{name} — Open-Hadith-Data #{c['number']} (not standard numbering)"
    return f"{name} {c['number']}"


def ref_html(c: dict) -> str:
    parts = [esc(ref(c))]
    if c.get("kitab"):
        parts.append(esc(c["kitab"]))
    parts.append(f"{c['containment']:.0%} of the book's text found")
    if c.get("url"):
        parts.append(f'<a href="{esc(c["url"])}" target="_blank" rel="noopener">sunnah.com ↗</a>')
    return " · ".join(parts)


def bold_runs(tokens: list[str]) -> list[tuple[str, bool]]:
    """Strip the **bold** markers, returning each token with whether it is bold."""
    out, bold = [], False
    for tok in tokens:
        if tok.startswith("**"):
            bold, tok = True, tok[2:]
        is_bold = bold
        if tok.endswith("**"):
            bold, tok = False, tok[:-2]
        out.append((tok, is_bold))
    return out


def vocalized_html(words: list[dict]) -> str:
    out = []
    for w, (tok, bold) in zip(words, bold_runs([w["text"] for w in words])):
        cls = " ".join(c for c in (WORD_CLASS.get(w["flag"]), "b" if bold else None) if c)
        out.append(f'<span class="{cls}">{esc(tok)}</span>' if cls else esc(tok))
    return " ".join(out)


def author_block(b: dict) -> str:
    text = " ".join(f'<b>{esc(t)}</b>' if bold else esc(t) for t, bold in bold_runs(b["text"].split()))
    notes = "".join(f'<p class="note">Note: {reason_html(n)}</p>' for n in b["transcriber_notes"])
    return f"""
    <section class="card author">
      <header><h3 class="ar" lang="ar" dir="rtl">{esc(b['heading'])}</h3>
        <span class="status author">The Sheikh's own text · {esc(b['kind'])}</span></header>
      <p class="meta">Book p. {b['book_page']} · not vocalized</p>
      <p class="ar text" lang="ar" dir="rtl">{text}</p>{notes}
    </section>"""


def plain_words(text: str) -> list[str]:
    """Words without tashkeel, punctuation or markers, for a search query."""
    out = []
    for w in expand_salutation(text.replace("**", "")).split():
        w = re.sub(r"[^\u0621-\u064A]", "", TASHKEEL.sub("", w))
        if w:
            out.append(w)
    return out


def dorar_link(words: list[str], label: str = "dorar.net ↗") -> str:
    if not words:
        return ""
    q = urllib.parse.quote(" ".join(words))
    return f'<a href="https://dorar.net/hadith/search?q={q}" target="_blank" rel="noopener">{label}</a>'


def context_words(text: str, phrase: str, k: int = 3) -> list[str]:
    """The phrase with k words of context on each side, from the entry's text."""
    ws, ps = plain_words(text), plain_words(phrase)
    for i in range(len(ws) - len(ps) + 1):
        if ws[i:i + len(ps)] == ps:
            return ws[max(0, i - k):i + len(ps) + k]
    return ps


def correction_row(c: dict, entry: dict, mode: str) -> str:
    level = "clear" if c["confidence"] >= 0.9 else "possible"
    n = entry["number"]
    if mode == "question":
        control = (f'<label><input type="radio" name="q{c["id"]}" value="approve" data-id="{c["id"]}"> Approve</label> '
                   f'<label><input type="radio" name="q{c["id"]}" value="reject" data-id="{c["id"]}"> Reject</label>')
    else:
        control = f'<label><input type="checkbox" name="u{c["id"]}" value="undo" data-id="{c["id"]}"> Undo</label>'
    link = dorar_link(context_words(corrected(entry, c["field"]), c["corrected"]))
    return f"""<tr>
      <td>{c['id']}</td><td><a href="#e{n}">{n}</a></td>
      <td>{ar(c['printed'].replace("**", ""))}</td><td>{ar(c['corrected'].replace("**", ""))}</td>
      <td><span class="chip {level}">{c['confidence']:.0%}</span></td>
      <td class="reason">{reason_html(c['reason'])} {link}</td>
      <td class="decide">{control}</td></tr>"""


def kept_row(k: dict) -> str:
    printed = " ".join(k["printed_words"]) or "—"
    alternative = " ".join(k["alternative_words"]) or "—"
    link = dorar_link(k.get("left", [])[-3:] + k["printed_words"] + k.get("right", [])[:3], "dorar.net: book's wording ↗")
    return f"""<tr><td><a href="#e{k['entry']}">{k['entry']}</a></td>
      <td>{ar(printed)}</td><td>{ar(alternative)}</td>
      <td class="reason">{reason_html(k['evidence'])} {link}</td></tr>"""


def reason_html(reason: str) -> str:
    # Wrap «quoted Arabic» so it gets the Arabic font and direction.
    out, rest = [], reason
    while "«" in rest and "»" in rest[rest.index("«"):]:
        start = rest.index("«")
        end = rest.index("»", start)
        out.append(esc(rest[:start]))
        out.append(f'<bdi class="ar" lang="ar">«{esc(rest[start + 1:end])}»</bdi>')
        rest = rest[end + 1:]
    out.append(esc(rest))
    return "".join(out)


def card(entry: dict, result: dict, voc: dict) -> str:
    title = f"({entry['number']}) {voc['heading']}" + (f" ({entry['label']})" if entry["label"] else "")
    meta = [ar(entry["citation"]), f"Book p. {entry['book_page']}"]
    if entry["grading"]:
        meta.append("Grading: " + ar(entry["grading"]))
    body = []
    best = result["match"]
    text = corrected(entry, "text")
    hadith = text[text.index("**"):] if "**" in text else text
    search = dorar_link(plain_words(hadith)[:8], "search on dorar.net ↗")
    if best:
        body.append(f'<p class="ref">{ref_html(best)} · {search}</p>')
    else:
        cited = COLLECTION_NAMES.get(result["cited_collection"], result["cited_collection"])
        body.append(f'<p class="ref">{esc(cited)} is not in either database, so this entry has no tashkeel '
                    f"except the book's own marks. {search}</p>")
    body.append(f'<p class="ar text" lang="ar" dir="rtl">{vocalized_html(voc["words"])}</p>')

    for c in entry["corrections"]:
        if c["status"] == "proposed":
            verb = f"Question {c['id']} ({c['confidence']:.0%})"
        elif c["status"] == "approved":
            verb = (f"Corrected automatically ({c['confidence']:.0%})" if c.get("decided_by") == "auto"
                    else "Correction approved by you")
        else:
            verb = "Correction rejected"
        body.append(f'<p class="corr {c["status"]}"><b>{verb}</b> ({esc(c["field"])}): '
                    f'{ar(c["printed"].replace("**", ""))} → {ar(c["corrected"].replace("**", ""))} — '
                    f'{reason_html(c["reason"])}</p>')
    for note in entry["transcriber_notes"]:
        body.append(f'<p class="note">Note: {reason_html(note)}</p>')

    compare_with = best or (result["other_collections"][0] if result["other_collections"] else None)
    if compare_with:
        book_html, db_html = diff(corrected(entry, "text"), compare_with["text"])
        label = "Compare with the database" if best else "Closest hadith in another collection (for reference only)"
        body.append(f"""<details><summary>{label}</summary>
          {'' if best else f'<p class="note">{ref_html(compare_with)}</p>'}
          <div class="compare">
            <div><h4>Book</h4><p class="ar small" lang="ar" dir="rtl">{book_html}</p></div>
            <div><h4>Database</h4><p class="ar small" lang="ar" dir="rtl">{db_html}</p></div>
          </div></details>""")
    notes = ([entry["takhrij"]] if entry["takhrij"] else []) + entry["footnotes"]
    if notes:
        items = "".join(f"<li>{ar(n, 'span')}</li>" for n in notes)
        body.append(f"<details><summary>Footnotes ({len(notes)})</summary><ul class=\"ar-list\">{items}</ul></details>")
    return f"""
    <section class="card" id="e{entry['number']}">
      <header><h3 class="ar" lang="ar" dir="rtl">{esc(title)}</h3>
        <span class="status {result['status']}">{STATUS_TEXT[result['status']]}</span></header>
      <p class="meta">{' · '.join(meta)}</p>
      {''.join(body)}
    </section>"""


def page(book: dict, matches: dict, vocalized: dict, misprints: list, book_slug: str = "") -> str:
    results = {r["number"]: r for r in matches["results"]}
    voc = {v["number"]: v for v in vocalized["entries"]}
    entries = book["entries"]

    seen, proposed, automatic = set(), [], []
    for e in entries:
        for c in e["corrections"]:
            if c["id"] in seen:
                continue
            seen.add(c["id"])
            if c["status"] == "proposed":
                proposed.append((c, e["number"]))
            elif c.get("decided_by") == "auto":
                automatic.append((c, e["number"]))
    kept = [k for k in misprints if k["decision"] in ("kept", "variant")]
    totals = {}
    for v in vocalized["entries"]:
        for k, n in v["counts"].items():
            totals[k] = totals.get(k, 0) + n
    matched = sum(1 for r in matches["results"] if r["match"])
    unmatched = [str(r["number"]) for r in matches["results"] if not r["match"]]

    by_number = {e["number"]: e for e in entries}
    decisions = "".join(correction_row(c, by_number[n], "question") for c, n in proposed) or \
        '<tr><td colspan="7">No questions for this chapter.</td></tr>'
    auto_rows = "".join(correction_row(c, by_number[n], "auto") for c, n in automatic) or \
        '<tr><td colspan="7">None.</td></tr>'
    kept_rows = "".join(kept_row(k) for k in kept) or '<tr><td colspan="4">None.</td></tr>'
    skipped = "".join(f"<li>Pages {esc(s['pages'])}: {reason_html(s['what'])}</li>" for s in book["skipped"])
    notes = "".join(f"<li>{reason_html(n)}</li>" for n in book["notes"])
    blocks = {}
    for b in book.get("author_text", []):
        blocks.setdefault(b["after_entry"], []).append(b)
    cards = "".join(author_block(b) for b in blocks.get(None, []))
    for e in entries:
        cards += card(e, results[e["number"]], voc[e["number"]])
        cards += "".join(author_block(b) for b in blocks.get(e["number"], []))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Chapter Review — {esc(book["chapter"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #faf8f4; --surface: #ffffff; --text: #1f1d1a; --muted: #6b665e; --border: #e4dfd6;
    --mark: #fde68a; --accent: #0f6b5c; --none: #8a8378;
    --ok: #1b7f4b; --ok-bg: #e3f4ea; --warn: #9a6200; --warn-bg: #fdf1d8; --bad: #a3322b; --bad-bg: #fbe5e3;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #161513; --surface: #1f1e1b; --text: #ece8e1; --muted: #a39d93; --border: #34312c;
      --mark: #6b5310; --accent: #5cc4ae; --none: #8f897f;
      --ok: #7ed3a2; --ok-bg: #1d3327; --warn: #f0c060; --warn-bg: #3a2f14; --bad: #f19a92; --bad-bg: #3d2120;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 1000px; margin: 0 auto; padding: 24px 16px 64px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.15rem; margin: 32px 0 8px; }}
  .ar {{ font-family: "Amiri", "Noto Naskh Arabic", serif; }}
  a {{ color: var(--accent); }}
  .table-wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); }}
  th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
  td .ar {{ font-size: 1.15em; white-space: nowrap; }}
  td.reason {{ min-width: 260px; color: var(--muted); font-size: 0.9rem; }}
  .chip, .status {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 0.8rem; white-space: nowrap; }}
  .chip.clear, .status.matched {{ color: var(--ok); background: var(--ok-bg); }}
  .chip.possible, .status.ambiguous, .status.check {{ color: var(--warn); background: var(--warn-bg); }}
  .status.not_found, .status.not_in_dataset {{ color: var(--bad); background: var(--bad-bg); }}
  .legend span {{ margin-inline-end: 16px; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; margin: 16px 0; }}
  .card header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .card h3 {{ margin: 0; font-size: 1.35rem; }}
  .meta, .note, .ref {{ color: var(--muted); margin: 6px 0; font-size: 0.9rem; }}
  .ref {{ color: var(--text); }}
  p.text {{ font-size: 1.45rem; line-height: 2.2; margin: 12px 0; text-align: justify; }}
  p.small {{ font-size: 1.15rem; line-height: 2; margin: 0; }}
  .near {{ background: var(--mark); border-radius: 3px; }}
  .none {{ color: var(--none); text-decoration: underline dotted; text-underline-offset: 6px; }}
  .bad {{ color: var(--bad); background: var(--bad-bg); border-radius: 3px; }}
  .b {{ font-weight: 700; }}
  td.decide {{ white-space: nowrap; font-size: 0.9rem; }}
  td.decide label {{ display: block; cursor: pointer; }}
  .copybar {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin: 16px 0 4px; }}
  .copybar button {{ font: inherit; padding: 6px 14px; border-radius: 6px; border: 1px solid var(--accent);
                    background: var(--accent); color: var(--surface); cursor: pointer; }}
  .copybar code {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 6px 10px; }}
  p.text {{ font-weight: 400; }}
  .card.author {{ border-style: dashed; }}
  .status.author {{ color: var(--muted); background: var(--bg); }}
  mark {{ background: var(--mark); color: inherit; border-radius: 3px; padding: 0 2px; }}
  .corr {{ margin: 6px 0; padding: 8px 12px; border-radius: 6px; font-size: 0.92rem; }}
  .corr.proposed {{ background: var(--warn-bg); }}
  .corr.approved {{ background: var(--ok-bg); }}
  .corr.rejected {{ background: var(--bg); color: var(--muted); }}
  .corr .ar, .reason .ar, .note .ar {{ font-size: 1.15em; }}
  .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px; }}
  .compare h4 {{ margin: 0 0 4px; font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }}
  details {{ margin-top: 10px; font-size: 0.9rem; }}
  summary {{ cursor: pointer; color: var(--muted); }}
  ul.ar-list {{ direction: rtl; padding-right: 20px; font-size: 1.05rem; line-height: 1.9; }}
  @media (max-width: 720px) {{ .compare {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
  <h1>Chapter review: {ar(book["chapter"])}</h1>
  <p class="meta">Book pages {book["book_pages"][0]}–{book["book_pages"][1]} · {len(entries)} entries ·
  {matched} matched to a database · {len(automatic)} corrected automatically · {len(proposed)} questions ·
  {totals.get("none", 0)} words left without tashkeel · {totals.get("near_difference", 0)} words to check</p>

  <h2>Questions for you</h2>
  <p class="meta">Possible misprints I'm less than 90% sure about. The book's printed text stays unless you approve.
  Choose Approve or Reject for each, then use “Copy my decisions” below.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Entry</th><th>Printed</th><th>Proposed</th><th>Confidence</th><th>Evidence</th><th>Your decision</th></tr></thead>
    <tbody>{decisions}</tbody>
  </table></div>

  <h2>Corrected automatically</h2>
  <p class="meta">Misprints with 90% confidence or more, already applied. Tick Undo to restore the printed text.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Entry</th><th>Printed</th><th>Corrected</th><th>Confidence</th><th>Evidence</th><th>Your decision</th></tr></thead>
    <tbody>{auto_rows}</tbody>
  </table></div>

  <div class="copybar">
    <button type="button" id="copy">Copy my decisions</button>
    <code id="summary">Nothing chosen yet.</code>
  </div>
  <p class="meta">Paste the copied line into the chat. Your choices are remembered on this computer until you change them.</p>

  <h2>Differences kept as printed</h2>
  <p class="meta">The book differs from the matched hadith here, but these are genuine variants, so the book's wording stays.</p>
  <div class="table-wrap"><table>
    <thead><tr><th>Entry</th><th>Book</th><th>Matched hadith</th><th>Why kept</th></tr></thead>
    <tbody>{kept_rows}</tbody>
  </table></div>

  <h2>How to read the text</h2>
  <p class="legend meta">
    <span class="b">Bold: the Companion's report and the hadith (the chain of narrators is regular)</span>
    <span>Normal: tashkeel from the matched hadith</span>
    <span class="none">No tashkeel: no matching word</span>
    <span class="near">Check the ending: next to a difference</span>
    <span class="bad">Conflict with the book's own marks</span></p>
  <p class="meta">Entries {", ".join(unmatched) or "—"} cite books that are in neither database, so they have
  no tashkeel except the book's own marks.</p>

  <h2>Chapter notes</h2>
  <ul>{notes}{skipped}</ul>

  <h2>Entries</h2>
  {cards}
  <p class="meta">Sources: book by Sheikh Mustafa al-Adawi · tashkeel from
  <a href="https://github.com/fawazahmed0/hadith-api">hadith-api</a> (Unlicense) and
  <a href="https://github.com/mhashim6/Open-Hadith-Data">Open-Hadith-Data</a> (ODbL).</p>
</main>
<script>
(function () {{
  const chapter = {json.dumps(book_slug)};
  const key = "azkar-decisions-" + chapter;
  const inputs = Array.from(document.querySelectorAll("input[data-id]"));
  function summary() {{
    const groups = {{ approve: [], reject: [], undo: [] }};
    inputs.filter(i => i.checked).forEach(i => groups[i.value].push(i.dataset.id));
    const parts = Object.entries(groups).filter(([, ids]) => ids.length).map(([verb, ids]) => verb + " " + ids.join(", "));
    return parts.length ? chapter + ": " + parts.join(" · ") : "";
  }}
  function refresh() {{
    const text = summary();
    document.getElementById("summary").textContent = text || "Nothing chosen yet.";
    try {{ localStorage.setItem(key, JSON.stringify(inputs.filter(i => i.checked).map(i => i.name + "=" + i.value))); }} catch (e) {{}}
  }}
  try {{
    const saved = JSON.parse(localStorage.getItem(key) || "[]");
    inputs.forEach(i => {{ if (saved.includes(i.name + "=" + i.value)) i.checked = true; }});
  }} catch (e) {{}}
  inputs.forEach(i => i.addEventListener("change", refresh));
  document.getElementById("copy").addEventListener("click", async () => {{
    const text = summary();
    if (!text) return;
    try {{ await navigator.clipboard.writeText(text); }}
    catch (e) {{
      const range = document.createRange(); range.selectNodeContents(document.getElementById("summary"));
      const sel = getSelection(); sel.removeAllRanges(); sel.addRange(range); document.execCommand("copy");
    }}
    document.getElementById("copy").textContent = "Copied";
    setTimeout(() => document.getElementById("copy").textContent = "Copy my decisions", 1500);
  }});
  refresh();
}})();
</script>
</body>
</html>
"""


def write_index() -> None:
    """.cache/reports/index.html: every chapter, with its counts and a link to its review page."""
    import csv
    rows = []
    for ch in csv.DictReader((ROOT / "content" / "book" / "chapters.tsv").open(encoding="utf-8"), delimiter="\t"):
        path = ROOT / "content" / "book" / f"{ch['slug']}.json"
        page_exists = (OUT_DIR / f"{ch['slug']}.html").exists()
        if path.exists():
            book = json.loads(path.read_text(encoding="utf-8"))
            seen, auto, questions = set(), 0, 0
            for e in book["entries"]:
                for c in e["corrections"]:
                    if c["id"] in seen:
                        continue
                    seen.add(c["id"])
                    auto += c.get("decided_by") == "auto" and c["status"] == "approved"
                    questions += c["status"] == "proposed"
            counts = (f"{len(book['entries'])} entries · {auto} corrected automatically · "
                      f"<b>{questions} questions</b>" if questions else
                      f"{len(book['entries'])} entries · {auto} corrected automatically · no questions")
        else:
            counts = "not transcribed yet"
        title = ar(ch["title"])
        link = f'<a href="{ch["slug"]}.html">{title}</a>' if page_exists else title
        rows.append(f"<tr><td>{ch['order']}</td><td>{link}</td><td>{ch['from_page']}–{ch['to_page']}</td><td>{counts}</td></tr>")
    html_page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Book Chapters</title>
<link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {{ --bg: #faf8f4; --surface: #fff; --text: #1f1d1a; --muted: #6b665e; --border: #e4dfd6; --accent: #0f6b5c; }}
  @media (prefers-color-scheme: dark) {{ :root {{ --bg: #161513; --surface: #1f1e1b; --text: #ece8e1;
    --muted: #a39d93; --border: #34312c; --accent: #5cc4ae; }} }}
  body {{ margin: 0; background: var(--bg); color: var(--text); font: 15px/1.5 system-ui, sans-serif; }}
  main {{ max-width: 900px; margin: 0 auto; padding: 24px 16px 64px; }}
  .ar {{ font-family: "Amiri", "Noto Naskh Arabic", serif; font-size: 1.15em; }}
  a {{ color: var(--accent); }}
  .wrap {{ overflow-x: auto; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); }}
  td, th {{ padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; }}
  p {{ color: var(--muted); }}
</style></head><body><main>
<h1>Book chapters</h1>
<p>Al-Sahih al-Musnad min Adhkar al-Yawm wal-Laylah · open a chapter to review it. Progress of the long run is in content/book/PROGRESS.md.</p>
<div class="wrap"><table><thead><tr><th>#</th><th>Chapter</th><th>Pages</th><th>Status</th></tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
</main></body></html>
"""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(html_page, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()
    book = load_chapter(args.name)
    matches = json.loads((ROOT / "content" / "matches" / f"{args.name}.json").read_text(encoding="utf-8"))
    vocalized = json.loads((ROOT / "content" / "vocalized" / f"{args.name}.json").read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}.html"
    misprints_path = ROOT / "content" / "matches" / f"{args.name}-misprints.json"
    misprints = json.loads(misprints_path.read_text(encoding="utf-8")) if misprints_path.exists() else []
    out.write_text(page(book, matches, vocalized, misprints, args.name), encoding="utf-8")
    write_index()
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
