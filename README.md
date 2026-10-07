# Azkar

A free, offline iPhone and Android app with the authentic azkar (remembrances) of the day and night, in Arabic and English.

All content comes from the book **الصحيح المسند من أذكار اليوم والليلة** (*Al-Sahih al-Musnad min Adhkar al-Yawm wal-Laylah*) by Sheikh Mustafa al-Adawi. The Sheikh has allowed his work to be used freely for the benefit of people.

## Status

Content pilot done on the Adhan chapter (book pages 35–47, entries 37–57): 19 of 21 entries matched a vocalized hadith automatically. The other 2 cite books that aren't in any database (Ibn Hibban, Abu 'Awana). No app code yet.

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

The book decides what is included: which hadith, under which chapter, with which grading. The vocalized Arabic text comes from hadith databases instead of being typed or OCR'd from the book.

1. **Index the book.** For each entry, record its number, sub-heading letter, chapter, the book's citation, the Sheikh's grading and the opening of the text.
2. **Match to a hadith database.** Search the collection the book cites for the closest text, then have a person confirm each match. Use the cited collection, since wording differs between collections. hadith-api is searched first; Open-Hadith-Data fills its gaps and adds Musnad Ahmad and Sunan al-Darimi.
3. **Fallback.** Entries from books not in either database (Ibn Hibban, Abu 'Awana, al-Nasa'i's *Amal al-Yawm wal-Layla*, Ibn al-Sunni, …) use the book's own text, with tashkeel added and reviewed.
4. **Prepare for the app.** Pull out the exact words to say, repeat counts and virtues. Assign sections and tags. Mark entries that are supporting hadith (virtues, rulings) rather than azkar to recite.
5. **Translate.** Write the English translation of the meaning and the transliteration, then have them reviewed.
6. **Review.** A person with Arabic and sharia knowledge checks every entry before release.

### Content tools

```
content/book/      transcribed book entries, one file per chapter (source of truth)
content/matches/   match results per chapter (generated, then reviewed)
tools/             Python scripts for the content pipeline
.cache/            downloads, page images and review pages (not in git)
```

```sh
python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt
.venv/bin/python tools/render_pages.py 35 48              # page images to transcribe from
.venv/bin/python tools/fetch_hadith.py                    # hadith databases (~215 MB, once)
.venv/bin/python tools/match.py content/book/adhan.json   # writes content/matches/adhan.json
.venv/bin/python tools/report.py adhan                    # writes .cache/reports/adhan.html
```

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
- Quran verses: [Tanzil](https://tanzil.net) (used unmodified, with attribution)
