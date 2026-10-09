# Azkar

A free, offline iPhone and Android app with the authentic azkar (remembrances) of the day and night, in Arabic and English.

All content comes from the book **الصحيح المسند من أذكار اليوم والليلة** (*Al-Sahih al-Musnad min Adhkar al-Yawm wal-Laylah*) by Sheikh Mustafa al-Adawi. The Sheikh has allowed his work to be used freely for the benefit of people.

## Status

Transcribing the book chapter by chapter. The index is transcribed (41 work units), the Adhan chapter (pp. 35–47, entries 37–57) is done and reviewed, and the long run over the remaining chapters is ready to start. No app code yet.

## Features

### Version 1

1. **Main sections:** Morning, Evening, After Prayer, Sleep & Waking, Adhan & Mosque, Home, Food, Travel, Distress & Illness, Istighfar, General Dhikr
2. **Browse by the book's chapters**, in the Sheikh's original order
3. **Dhikr card:** fully vocalized Arabic text, repeat count, virtue (فضل), source and the Sheikh's grading (صحيح / حسن), with a tap to show the full narration and chain of narrators
4. **Tap counter** on each dhikr that moves to the next one when a set is done, with progress through a session (e.g. the morning azkar)
5. **Vibration when a set is complete** (not on every tap)
6. **Free tasbih counter**
7. **English translation and transliteration**, each of which can be shown or hidden
8. **Arabic or English interface** (right-to-left / left-to-right)
9. **Search** in Arabic (ignores tashkeel and hamza forms) and in English
10. **Favorites**
11. **Reading settings:** font size, light / dark mode
12. **Share** a dhikr as text with its source, or as an image card
13. **Fully offline**, with no account, ads or tracking
14. **About screen** crediting the Sheikh and the book

### Later

- More languages (Urdu, Indonesian, French, Turkish, …)

## Content pipeline

The Sheikh's book is the source of truth for the wording of every hadith. The hadith databases are only used to find each hadith's standard reference number, to catch transcription mistakes and to supply tashkeel. Their wording never replaces the book's.

Each chapter goes through these steps:

1. **Transcribe exactly as printed:** the hadith with its chain of narrators (bold and regular type marked), the book's own tashkeel marks, the Sheikh's grading, the source references, footnotes about the hadith, and the Sheikh's own text in the main body. General commentary in footnotes is skipped and its pages are logged.
2. **Cross-check with OCR.** Tesseract reads the same pages. Every word where it disagrees, especially where my reading matches the database but the page shows otherwise, is checked on a zoomed crop. On the pilot this caught all 7 words written from memory.
3. **Match** each entry to the collection it cites. hadith-api is searched first; Open-Hadith-Data fills its gaps and adds Musnad Ahmad and Sunan al-Darimi.
4. **Find the book's misprints.** Every difference between an entry and its matched hadith is checked against all the hadith collections and dorar.net:
   - the printed wording is attested elsewhere, or is a usual narration variant → kept as printed
   - a likely misprint with confidence of 90% or more → corrected automatically (shown on the review page with an Undo box)
   - below 90% → the owner is asked, unless it is a clear grammar mistake the transcriber can judge
   The printed text is always kept next to a correction.
5. **Add tashkeel** to the book's text. The book's own marks always win. Words identical to the matched hadith take its tashkeel. Words without a match are left without tashkeel rather than risk a wrong one. Words next to a difference are flagged, because their endings can depend on it.
6. **Review** the chapter page: questions, automatic corrections, kept differences, with dorar.net links for cross-checking.

`tools/pipeline.py <chapter>` runs steps 2–6 after the transcription. The long run (`tools/long_run.sh`) does one chapter per fresh Claude Code session, in the order of `content/book/PROGRESS.md`, and waits out usage-limit resets.

After all chapters are done:

7. **Prepare for the app.** Pull out the exact words to say, repeat counts and virtues. Assign sections and tags. Mark entries that are supporting hadith (virtues, rulings) rather than azkar to recite.
8. **Translate.** Write the English translation of the meaning and the transliteration, then have them reviewed.
9. **Final review.** A person with Arabic and sharia knowledge checks every entry before release.

### Content tools

The detailed transcription rules are in [docs/transcription.md](docs/transcription.md).

```
content/book/index.tsv     the book's index (فهرس, pp. 447–470): every heading and its page
content/book/chapters.tsv  the 41 work units (chapters) with their pages and file names
content/book/PROGRESS.md   the long run's order and status
content/book/              transcribed book entries and corrections, one file per chapter (source of truth)
content/matches/           matched hadith for each entry (generated)
content/vocalized/         the book's text with tashkeel added, word by word (generated)
tools/                     Python scripts for the content pipeline
.cache/                    downloads, page images and review pages (not in git)
```

```sh
python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
tools/fetch_ocr.sh                                         # Tesseract OCR into .cache/ocr (nothing installed system-wide)
.venv/bin/python tools/fetch_hadith.py                     # hadith databases (~215 MB, once)
.venv/bin/python tools/render_pages.py 35 47 --dpi 220 --strips 2   # zoomed page images to transcribe from
.venv/bin/python tools/zoom.py 41 0.30 0.35                # a closer look at part of a page
.venv/bin/python tools/pipeline.py adhan                   # check, match, OCR cross-check, misprints, tashkeel, review page
tools/long_run.sh                                          # the long run: one chapter per session until all are done
```

The pipeline's steps can also be run one by one: `check.py`, `match.py`, `ocr.py FIRST LAST`, `ocr_check.py --crops`, `misprints.py`, `vocalize.py`, `report.py`. Review pages are in `.cache/reports/` (`index.html` lists every chapter).

### Notes on the source book

- PDF: <http://mostafaaladwy.com/upload/books/azkar.pdf>
- 470 scanned pages with no text layer, so the book can only be read with OCR.
- The index (فهرس) starts on page 447.
- Each entry gives its source, the full chain of narrators, the text in bold and the Sheikh's grading, followed by footnotes with more references.
- Most citations give the volume and page of a specific printed edition (e.g. أبو داود ج١ ص٣٣٧; Bukhari via *Fath al-Bari*; Muslim via al-Nawawi's commentary). Ibn Majah is cited by hadith number.
- Letters such as (أ)، (ب) number the items under a heading and restart at each heading.
- Example match: entry (٤٥) is Sunan Abi Dawud #499.

## Data

- **Source of truth:** JSON files in this repo, one record per entry, so changes are easy to review and correct.
- **In the app:** a build script turns the JSON into a SQLite database that ships with the app, with full-text search.
- **Search:** each text also gets a simplified copy for searching (tashkeel removed, أ/إ/آ → ا, ة → ه, ى → ي).
- **User data** (favorites, counters, settings) is stored separately so content updates never erase it.

Each entry record holds:

- the book's entry number and sub-heading letter
- chapter, sections and tags
- the words to say, the repeat count and the virtue
- the full narration
- the source collection and hadith number, plus the book's citation
- the grading
- the English translation and transliteration
- notes

## Tech stack

- **React Native + Expo (TypeScript):** one codebase for iPhone and Android. Expo's cloud build service (EAS) builds and submits the iPhone app without needing a Mac.
- **expo-sqlite** for the bundled database.

## Release

- Apple Developer account ($99/year) and Google Play developer account ($25 one-time)
- Privacy policy (required by both stores, even though the app collects no data)
- Store listings and screenshots in Arabic and English

## Sources and credits

- Book, selection and gradings: Sheikh Mustafa al-Adawi, <https://mostafaaladwy.com>
- Vocalized hadith text: [fawazahmed0/hadith-api](https://github.com/fawazahmed0/hadith-api) (public domain, Unlicense) and [mhashim6/Open-Hadith-Data](https://github.com/mhashim6/Open-Hadith-Data) (ODbL; a database we publish that is built from it must also be shared under ODbL)
- Cross-checking wordings and misprints: [Dorar al-Saniyya hadith encyclopedia](https://dorar.net/hadith) (dorar.net, through its public search API)
- Quran verses: [Tanzil](https://tanzil.net) (used unmodified, with attribution)
