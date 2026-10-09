# Long run: one round

`tools/long_run.sh` starts a fresh Claude Code session for each round with the prompt "Do one round of the long run: follow docs/long-run.md exactly." A round works on one chapter and transcribes at most 5 pages, then stops, so every round starts with the rules freshly read instead of a summary of them. Rounds are kept short because every step re-reads everything the session has read so far, so a step late in a long round costs many times one early in a short round. Each round starts with no memory of earlier rounds, so everything it needs is in files.

1. **Read** `CLAUDE.md`, `docs/transcription.md` (the rules: follow them exactly) and `content/book/PROGRESS.md`. Read nothing more than the round needs, because everything read stays in the session. The tools' usage is in `docs/transcription.md`, so don't read their source. Don't read other chapters' files whole: the format is in `docs/transcription.md`, and if you want an example, the first 80 lines of `content/book/adhan.json` are enough. The chapter you're working on you read in full.
2. **Pick** the first chapter in `PROGRESS.md` whose status is `in progress`, `transcribed` or `todo`, in the table's order. Skip `blocked` chapters: they wait for the owner. If its status is `transcribed`, go straight to step 4.
3. **Transcribe** it following `docs/transcription.md`, page by page:
   - Render pages with `tools/render_pages.py`, and zoom with `tools/zoom.py` whenever a word or mark is doubtful, a page's doubtful spots in one batch (see step 2 of the workflow in `docs/transcription.md`).
   - After each page, save the entries finished so far to `content/book/<slug>.json`. Keep it valid JSON, and set `book_pages` to the pages done so far. Then set the chapter's status in `PROGRESS.md` to `in progress (through p. N)`. A round can be cut off at any moment by a usage limit. The next round resumes right after the last saved entry (or `author_text` block), which may be on page N itself, because an entry that runs onto the next page isn't saved until it's complete.
   - An entry that continues onto the next page is saved only once it's complete.
   - When the chapter's last page is saved, set its status to `transcribed` and stop. The pipeline and the review are the next round's work.
   - After 5 pages in this round, stop, even in the middle of the chapter. The next round continues it.
4. **When the chapter is transcribed,** run `.venv/bin/python tools/pipeline.py <slug>`, then:
   - Look at every OCR flag sheet in `.cache/ocr/flags/<slug>/` and fix real transcription mistakes.
   - Check on the scan every line of the misprints output marked `check-scan` (the OCR reads the database's word, so the transcription may be wrong) or `unknown` (a word found in no collection). They are also in `content/matches/<slug>-misprints.json`. Fix the transcription if it's wrong. If the page really prints a clear misprint, propose a correction by hand, per "Corrections" in `docs/transcription.md`.
   - Review the questions, per "Corrections" in `docs/transcription.md`. Approve the clear grammar mistakes yourself; leave the rest for the owner.
   - If you fixed a word inside an automatic correction (`decided_by: auto` without `source`), `check.py` reports that its printed text no longer occurs. Delete that correction: the pipeline works it out again.
   - After any change, rerun the pipeline, so the review page and `content/vocalized/` show the final state. Take the counts for step 5 from that last run.
5. **Mark it done** in `PROGRESS.md`: `done: N entries, A corrected automatically, Q questions`.
6. **Stop.** If no chapter is left `todo`, `in progress` or `transcribed`, change the line `Status: running` to `Status: ALL DONE`.

**If a chapter can't be finished** for a reason only the owner can fix (a tool fails on it in a way no edit under `content/` fixes, or a page can't be read), set its status to `blocked: <short reason>`, explain under "Notes for the owner" in `PROGRESS.md`, and stop. The next round moves on to the next chapter, so the run never repeats the same failure.

**What a round may do.** Read any file, edit files under `content/`, and run the project's tools as plain commands from the project folder, e.g. `.venv/bin/python tools/zoom.py 96 0.30 0.35`. Write no `cd`, pipes, `python -c` or other shell commands: anything else is refused, because nobody is there to approve it.

Never commit to git, and never change `docs/` or `tools/` during the run. If a rule or a tool seems wrong, describe it under "Notes for the owner" in `PROGRESS.md` and carry on with the rules as they are.
