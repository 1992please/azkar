"""Build an HTML review page for one chapter's matches.

Usage: python tools/report.py adhan

Reads content/book/<name>.json and content/matches/<name>.json, writes
.cache/reports/<name>.html. Words that differ between the book and the
matched hadith are highlighted on both sides.
"""

import argparse
import difflib
import html
import json
import pathlib

from arabic import expand_salutation, normalize_word

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
    "ambiguous": "Matched, but close alternatives",
    "check": "Partial match — check",
    "not_found": "Not found",
    "not_in_dataset": "Cited book not in database",
}


def diff(book_text: str, db_text: str) -> tuple[str, str]:
    """Return both texts as HTML with differing words wrapped in <mark>."""
    a = [(w, normalize_word(w)) for w in expand_salutation(book_text).split()]
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
        return " ".join(f"<mark>{html.escape(w)}</mark>" if i in marked else html.escape(w)
                        for i, (w, _) in enumerate(tokens))
    return render(a, a_marked), render(b, b_marked)


def ref(c: dict) -> str:
    name = COLLECTION_NAMES.get(c["collection"], c["collection"])
    if c["source"] == "open-hadith-data":
        return f"{name} — Open-Hadith-Data #{c['number']} (not standard numbering)"
    return f"{name} {c['number']}"


def ref_html(c: dict) -> str:
    parts = [html.escape(ref(c))]
    if c.get("kitab"):
        parts.append(html.escape(c["kitab"]))
    parts.append(f"{c['containment']:.0%} of the book's text found")
    if c.get("url"):
        parts.append(f'<a href="{html.escape(c["url"])}" target="_blank" rel="noopener">sunnah.com ↗</a>')
    return " · ".join(parts)


def comparison(entry: dict, c: dict) -> str:
    book_html, db_html = diff(entry["text"], c["text"])
    return f"""
      <div class="compare">
        <div><h4>Book (transcribed)</h4><p class="ar" lang="ar" dir="rtl">{book_html}</p></div>
        <div><h4>Database (vocalized)</h4><p class="ar" lang="ar" dir="rtl">{db_html}</p></div>
      </div>"""


def card(entry: dict, result: dict) -> str:
    status = result["status"]
    title = f"({entry['number']}) {entry['heading']}" + (f" ({entry['label']})" if entry["label"] else "")
    meta = [f'<span class="ar" lang="ar" dir="rtl">{html.escape(entry["citation"])}</span>',
            f"Book p. {entry['book_page']}"]
    if entry["grading"]:
        meta.append(f'Grading: <span class="ar" lang="ar">{html.escape(entry["grading"])}</span>')
    body = []
    best = result["match"]
    if best:
        body.append(f'<p class="ref">{ref_html(best)}</p>')
        if result["same_text_also_at"]:
            body.append(f'<p class="note">Same text also at: {html.escape(", ".join(result["same_text_also_at"]))}</p>')
        body.append(comparison(entry, best))
    else:
        cited = COLLECTION_NAMES.get(result["cited_collection"], result["cited_collection"])
        reason = ("isn't in either database" if status == "not_in_dataset" else "has no close match")
        body.append(f'<p class="ref">{html.escape(cited)} {reason}. '
                    'The book\'s own text will be used, with tashkeel added and reviewed.</p>')
        if result["other_collections"]:
            other = result["other_collections"][0]
            body.append(f'<p class="note">Closest hadith in another collection: {ref_html(other)}</p>')
            body.append(comparison(entry, other))
        else:
            body.append(f'<p class="ar solo" lang="ar" dir="rtl">{html.escape(entry["text"])}</p>')
    extra = [c for c in result["alternatives"]] + ([] if not best else result["other_collections"])
    if extra:
        items = "".join(f"<li>{ref_html(c)}</li>" for c in extra)
        body.append(f"<details><summary>Other candidates ({len(extra)})</summary><ul>{items}</ul></details>")
    for note in entry["transcriber_notes"]:
        body.append(f'<p class="note">Note: {html.escape(note)}</p>')
    return f"""
    <section class="card" id="e{entry['number']}">
      <header>
        <h3 class="ar" lang="ar" dir="rtl">{html.escape(title)}</h3>
        <span class="status {status}">{STATUS_TEXT[status]}</span>
      </header>
      <p class="meta">{' · '.join(meta)}</p>
      {''.join(body)}
    </section>"""


def page(book: dict, matches: dict) -> str:
    results = {r["number"]: r for r in matches["results"]}
    entries = book["entries"]
    counts = {}
    for r in matches["results"]:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    summary = " · ".join(f'<span class="status {s}">{STATUS_TEXT[s]}: {n}</span>' for s, n in counts.items())
    rows = "".join(
        f'<tr><td><a href="#e{e["number"]}">{e["number"]}</a></td>'
        f'<td class="ar" lang="ar" dir="rtl">{html.escape(e["heading"])}</td>'
        f'<td>{html.escape(ref(results[e["number"]]["match"])) if results[e["number"]]["match"] else "—"}</td>'
        f'<td><span class="status {results[e["number"]]["status"]}">{STATUS_TEXT[results[e["number"]]["status"]]}</span></td></tr>'
        for e in entries)
    notes = "".join(f"<li>{html.escape(n)}</li>" for n in book["notes"])
    cards = "".join(card(e, results[e["number"]]) for e in entries)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Match Review — {html.escape(book["chapter"])}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Amiri:wght@400;700&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #faf8f4; --surface: #ffffff; --text: #1f1d1a; --muted: #6b665e; --border: #e4dfd6;
    --mark: #fde68a; --accent: #0f6b5c;
    --ok: #1b7f4b; --ok-bg: #e3f4ea; --warn: #9a6200; --warn-bg: #fdf1d8; --bad: #a3322b; --bad-bg: #fbe5e3;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #161513; --surface: #1f1e1b; --text: #ece8e1; --muted: #a39d93; --border: #34312c;
      --mark: #6b5310; --accent: #5cc4ae;
      --ok: #7ed3a2; --ok-bg: #1d3327; --warn: #f0c060; --warn-bg: #3a2f14; --bad: #f19a92; --bad-bg: #3d2120;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: var(--bg); color: var(--text);
         font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 64px; }}
  h1 {{ font-size: 1.5rem; margin: 0 0 4px; }}
  h2 {{ font-size: 1.1rem; margin: 32px 0 8px; }}
  .ar {{ font-family: "Amiri", "Noto Naskh Arabic", serif; }}
  h1 .ar {{ font-size: 1.15em; }}
  a {{ color: var(--accent); }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--border); }}
  th, td {{ padding: 6px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: middle; }}
  td.ar {{ text-align: right; font-size: 1.1em; }}
  .table-wrap {{ overflow-x: auto; }}
  .status {{ display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 0.8rem; white-space: nowrap; }}
  .status.matched {{ color: var(--ok); background: var(--ok-bg); }}
  .status.ambiguous, .status.check {{ color: var(--warn); background: var(--warn-bg); }}
  .status.not_found, .status.not_in_dataset {{ color: var(--bad); background: var(--bad-bg); }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
          padding: 16px; margin: 16px 0; }}
  .card header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .card h3 {{ margin: 0; font-size: 1.35rem; }}
  .meta, .note, .ref {{ color: var(--muted); margin: 6px 0; font-size: 0.9rem; }}
  .ref {{ color: var(--text); }}
  .compare {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 8px; }}
  .compare h4 {{ margin: 0 0 4px; font-size: 0.8rem; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }}
  p.ar {{ font-size: 1.3rem; line-height: 2.1; margin: 0; text-align: justify; }}
  mark {{ background: var(--mark); color: inherit; border-radius: 3px; padding: 0 2px; }}
  details {{ margin-top: 10px; font-size: 0.9rem; }}
  summary {{ cursor: pointer; color: var(--muted); }}
  @media (max-width: 720px) {{ .compare {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<main>
  <h1>Match review: <span class="ar" lang="ar">{html.escape(book["chapter"])}</span></h1>
  <p class="meta">Book pages {book["book_pages"][0]}–{book["book_pages"][1]} · {len(entries)} entries · {summary}</p>
  <p class="meta"><mark>Highlighted</mark> words differ between the book and the database text
  (spelling and tashkeel are ignored). Highlighted words in the database column that are missing from the book
  are usually extra chains of narrators or narrations that the database groups with the hadith.</p>
  <h2>Chapter notes</h2>
  <ul>{notes}</ul>
  <h2>Summary</h2>
  <div class="table-wrap"><table>
    <thead><tr><th>#</th><th>Heading</th><th>Matched hadith</th><th>Status</th></tr></thead>
    <tbody>{rows}</tbody>
  </table></div>
  <h2>Entries</h2>
  {cards}
  <p class="meta">Sources: book by Sheikh Mustafa al-Adawi · vocalized text from
  <a href="https://github.com/fawazahmed0/hadith-api">hadith-api</a> (Unlicense) and
  <a href="https://github.com/mhashim6/Open-Hadith-Data">Open-Hadith-Data</a> (ODbL).</p>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    args = parser.parse_args()
    book = json.loads((ROOT / "content" / "book" / f"{args.name}.json").read_text(encoding="utf-8"))
    matches = json.loads((ROOT / "content" / "matches" / f"{args.name}.json").read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{args.name}.html"
    out.write_text(page(book, matches), encoding="utf-8")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
