# Transcription rules

These rules apply to every chapter. They were agreed with the project owner; change them only with the owner's approval.

## The rule above all

**The book is the source of truth.** Transcribe exactly what is printed, word by word, from zoomed scans.

- Never write a hadith from memory, and never "fix" the wording to match a database or the well-known version. In the pilot, 7 words were written from memory instead of from the page. The database check can't catch these, because the mistake agrees with the database.
- Never add tashkeel yourself. Only the book's own marks are transcribed; the tools add the rest from the databases.
- If a word might differ from the famous wording, zoom in until you're sure what is printed.

## Per-chapter workflow

1. **Pick the chapter** from `content/book/chapters.tsv`. `from_page` is where its title is printed; `to_page` is where the next chapter's title is printed, so that page may be shared: stop at the next chapter's title.
2. **Render** the pages as zoomed strips and read every strip:
   `.venv/bin/python tools/render_pages.py FROM TO --dpi 220 --strips 2`
   Zoom further on small marks, digits in citations, names, and any doubtful word:
   `.venv/bin/python tools/zoom.py PAGE TOP BOTTOM [--left L --right R]` (fractions of the page; a line is about 0.03 high).
   - **Zoom in batches.** Every step re-reads the whole session so far, so many one-crop steps add up to most of a session's cost. While reading a page's strips, note its doubtful spots. Then render them all in one command, `.venv/bin/python tools/zoom.py PAGE --crop TOP BOTTOM [LEFT RIGHT] --crop TOP BOTTOM [LEFT RIGHT] …`, and read all the crops in one step (several Reads at once). Zoom again only on what is still unclear.
   - **Crop narrower for more detail; don't raise the dpi.** The Read tool shows an image at most 2000 px on its longer side, so a wide crop above about 330 dpi is scaled back down and shows nothing more. `zoom.py` picks the highest dpi that is shown in full, so leave out `--dpi`. A crop of one or two words is magnified up to 1600 dpi.
3. **Write** `content/book/<slug>.json` (format below).
4. **Run the pipeline:** `.venv/bin/python tools/pipeline.py <slug>`. It checks the file, matches entries, OCRs the pages, cross-checks the transcription against the OCR, detects misprints, vocalizes and builds the review page. Fix any checker error and rerun.
5. **Look at every OCR flag sheet** (`.cache/ocr/flags/<slug>/sheet-*.png`). Each line holds a word where the OCR disagrees with the transcription (headings, citations, entry texts and `author_text`; footnotes aren't checked, so read them with extra care). "memory" flags (my word matches the database but the OCR sees something else) are the most important. Fix real mistakes and rerun. The OCR check ignores tashkeel, hamza forms («أ إ آ ء»), final «ى»/«ي» and «ة»/«ه», so these are only as right as your reading: zoom on every printed mark, and on hamzas and word endings in the hadith text (the effort test's slips were all of this kind).
6. The review page (`file:///home/nader/projects/azkar/.cache/reports/<slug>.html`) is then ready for the owner. Only the questions need the owner's answer.

## What to transcribe

- **Every numbered entry:** the citation line, the full text (chain of narrators and hadith), the Sheikh's grading, the source-reference footnote and the footnotes about the hadith or its wording.
- **Inside an entry, keep in `text` as printed** (and say so in `transcriber_notes`): a further narration or chain printed without an entry number of its own, with its own citation line if it has one (bold or regular, as printed), and the Sheikh's own remarks before the grading (e.g. «قلت : …»). They are separated from the hadith when the content is prepared for the app.
- **Headings** exactly as printed; sub-heading letters such as (أ) go in `label`. A heading printed on two lines, a number and then a title (e.g. «الحرز الأول» over «صلاة أربع ركعات أول النهار»), is joined with « : », as in the index. A section heading with no text of its own (e.g. «ثانيا : …» above a sub-heading) is an `author_text` block of kind `heading` with empty `text`, after the entry before it.
- **Skip** general commentary that isn't about the hadith or its wording (e.g. the «تعقيب» on pp. 39–40), and log it in `skipped` with its pages.
- **The Sheikh's own text in the main body** (the preface, Quran verses quoted at the start of a chapter, lists, cross-references, essays) goes in `author_text`: `{"after_entry": <entry number or null>, "book_page", "heading", "kind": preface|verses|note|list|crossref|essay|heading, "text", "footnotes", "corrections", "transcriber_notes"}`. Its `heading` is the heading in effect, as for entries: the chapter title before the first sub-heading. It is not vocalized.
- **Bold:** wrap each run printed in bold in `**…**`, with the markers attached to the run's first and last word. The chain of narrators is normally regular type and the Companion's report plus the hadith bold; mark what the page shows.

## Text conventions

| What | Rule | Example |
|---|---|---|
| Letters | Exactly as printed, including final «ى» for «ي», «ابن» at the start of a line, hamza forms | «على بن عياش», «نودى», «فى» |
| Tashkeel | Only the book's own marks, exactly where printed | «علَّمه», «عليَّ», «سَلُوا», «آتِ» |
| Salutation glyph | Write ﷺ (U+FDFA). If the book uses another honorific glyph, ask before choosing a character | |
| Quoted speech | « » with spaces inside, as printed | « إذا سمعتم النداء » |
| Quran | ﴿ ﴾ with spaces inside; a surah that is only named, not quoted, gets none | ﴿ إن في خلق السموات ﴾ |
| Punctuation | Arabic comma «،» and question mark «؟»; colon «:» and full stop «.» with a space before and after | قال : « … » . |
| Dashes | A space on each side, whatever the printed spacing; a hyphen between two numbers (a range) stays attached | ميمونة - وهي خالته - قال · ٣٨١-٣٨٢ |
| Small upright alif | The dagger alif (U+0670) where printed | «السمٰوات» |
| Nisba mark | The mark printed over a nisba's final ya is a shadda | «النسائيّ» |
| Digits | Arabic-Indic, as printed | ج٢ ص٨٧ |
| Lines | Join printed lines into one paragraph | |
| Footnote markers | Not kept in the text (see footnotes below) | |

The checker rejects anything outside the expected characters: Persian look-alike letters (ی ک), Latin letters, ASCII digits, invisible marks and presentation forms.

## File format

`content/book/<slug>.json`, where `<slug>` comes from `chapters.tsv`:

```json
{
  "chapter": "the chapter title as printed",
  "book_pages": [35, 47],
  "notes": ["English notes about the chapter"],
  "skipped": [{ "pages": "39–40", "what": "what was skipped and why" }],
  "author_text": [ … ],
  "entries": [ … ]
}
```

Each entry:

| Field | Content |
|---|---|
| `number` | The book's entry number. Numbers run 1, 2, 3 … across the whole book with no gaps |
| `book_page` | Page where the entry's citation line is printed |
| `heading` | The heading in effect, as printed |
| `label` | Sub-heading letter (أ، ب، ج، د، هـ …) or `null` |
| `citation` | The citation line as printed, without the entry number or trailing colon |
| `source` | `collection` code (below) plus `volume`/`page` or `hadith` as cited; `edition` if named (e.g. «موارد الظمآن») |
| `text` | The full entry text as printed |
| `grading` | The grading printed after the entry, or `null` with a transcriber note |
| `takhrij` | The entry's numbered source-reference footnote, without its number, whole: its references and any narrations it quotes, its paragraphs joined; or `null` |
| `footnotes` | Other footnotes about the hadith, each starting with its marker and an anchor naming the words it belongs to: `(*) [على «…»] …` (the bracketed anchor is ours, not the book's). A footnote continued on the next page (starting with «=») is joined into one. An unnumbered paragraph printed after the source references that explains the hadith or its words is its own item, starting with the entry's footnote number (e.g. «(١٦٢)») |
| `corrections` | Proposed or decided corrections (below) |
| `transcriber_notes` | English notes: anything unusual, and why a field is empty |

**Collection codes:** `bukhari`, `muslim`, `abudawud`, `tirmidhi`, `nasai`, `ibnmajah`, `malik`, `ahmad`, `darimi` (in the databases); `ibnhibban`, `abuawana`, `nasai-kubra`, `ibnsunni`, `hakim`, `tabarani`, `bayhaqi`, `ibnabishaybah`, `abdurrazzaq`, `ibnkhuzaymah`, `bukhari-adab`, `other` (not in the databases). Add a new code to `COLLECTIONS` in `tools/check.py` and to this list.

Citations name printed editions: «فتح ج٢ ص٨٧» is Bukhari through *Fath al-Bari*, volume 2 page 87; «مسلم ج٤ ص٨٠ نووي» is Muslim through al-Nawawi's commentary; Ibn Majah is usually cited by hadith number.

## Corrections

A correction never changes the printed field; it is stored next to it and applied by the tools once approved. Its `field` is `text`, `heading`, `citation`, `takhrij`, or `footnotes.N` for the N-th item of `footnotes` (from 0).

`tools/misprints.py` finds them. It compares each entry with its matched hadith, checks whether the printed wording is attested anywhere in the collections or on dorar.net, and scores the rest:
- **attested elsewhere, or a typical narration variant** (prefix و ف ل ب ك, particle, transmission verb or its abbreviation such as «ثنا», spelling such as a long-vowel alif, a doubled waw or words written joined, word order, verb gender ending) → the book is kept, nothing is asked;
- **score ≥ 0.90** → approved automatically (`decided_by: "auto"`);
- **score < 0.90** → `proposed`, and the owner is asked.
- **always asked, whatever the score:** the alternative is attested nowhere in that context; the entry has no matched hadith (its source isn't in the databases, so its chain can't be compared); an attached pronoun is added or dropped outside a name («تطحنه» / «تطحن»), since either form can be grammatical.

```json
{ "id": 4, "field": "text", "printed": "ثم استأذن عني", "corrected": "ثم استأخر عني",
  "confidence": 0.91, "status": "approved", "decided_by": "auto", "reason": "evidence, in English" }
```

- `status`: `proposed`, `approved` or `rejected`. `decided_by`: `owner`, `auto`, or `null` while proposed. The owner's decisions are never changed by the tools; record them as `decided_by: "owner"` with the date in `reason`.
- A correction proposed by hand (e.g. a heading misprint) gets `"source": "transcriber"` so the tool keeps it.
- `printed` must occur exactly once in its field. The same correction on several entries shares one id. Numbers stay the same from run to run.

**Before leaving a question for the owner, judge it yourself.** If the printed form is clearly ungrammatical in context (e.g. a jussive verb with no particle governing it, a sentence missing its predicate) or is a narrator's name spelled in a way no narration uses, approve it yourself: `status: approved`, `decided_by: auto`, `source: transcriber`, confidence 0.90–0.95, and start `reason` with "Transcriber's judgment:" followed by the grammatical or name reason. Leave anything that depends on meaning, or is a real judgement call, for the owner.

**Footnote misprints.** An obvious misprint in a footnote (a book's title, a collection's or narrator's name, «ح» printed for «ج» before a volume number) is corrected the same way: a correction on `takhrij` or `footnotes.N`, approved by the transcriber, the printed form kept. The tool doesn't look for these, so note them while transcribing.

**A correction changes only the misprinted word.** If the tool's correction of a name also rewrites the words around it, narrow it to the name and approve it under the names rule with `source: transcriber`, so the tool keeps it; on the rerun the tool classes the rest as variants.

**The owner's answers so far** (the reference for this judgement): all five Adhan questions, scored 68–88%, were approved. They were a pronoun missing from the end of a sentence («أنا» → «أنا هو»), a word cut short that is quoted in full in the same hadith («وأن» → «وأنا»), a narrator's nisba no narration uses, «عن» printed for «بن» inside a chain, and a Companion's kunya missing its first letter («أبي سيد» → «أبي أسيد»). The owner noted that names and grammar mistakes are the easiest to recognise. The scoring now adds +0.10 for names and +0.05 for cut-off words.

**The review page** lets the owner tick Approve / Reject / Undo and copy the decisions as one line (e.g. `adhan: approve 5 · undo 3`). Apply such a line by setting each correction's `status`, with `decided_by: owner` and the date in `reason`. "Undo" means `status: rejected`.
