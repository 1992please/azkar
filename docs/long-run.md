# Long run: one round

`tools/long_run.sh` starts a fresh Claude Code session for each round with the prompt "Do one round of the long run: follow docs/long-run.md exactly." A round does at most one chapter, then stops. Each round starts with no memory of earlier rounds, so everything it needs is in files.

1. **Read** `CLAUDE.md`, `docs/transcription.md` (the rules: follow them exactly) and `content/book/PROGRESS.md`.
2. **Pick** the first chapter in `PROGRESS.md` whose status is `in progress` or `todo`, in the table's order. Skip `blocked` chapters: they wait for the owner.
3. **Transcribe** it following `docs/transcription.md`, page by page:
   - Render pages with `tools/render_pages.py`, and zoom with `tools/zoom.py` whenever a word or mark is doubtful.
   - After each page, save the entries finished so far to `content/book/<slug>.json`. Keep it valid JSON, and set `book_pages` to the pages done so far. Then set the chapter's status in `PROGRESS.md` to `in progress (through p. N)`. A round can be cut off at any moment by a usage limit. The next round resumes right after the last saved entry (or `author_text` block), which may be on page N itself, because an entry that runs onto the next page isn't saved until it's complete.
   - An entry that continues onto the next page is saved only once it's complete.
4. **When the chapter is complete,** run `.venv/bin/python tools/pipeline.py <slug>`, then:
   - Look at every OCR flag sheet in `.cache/ocr/flags/<slug>/`, fix real transcription mistakes, and rerun the pipeline.
   - Review the questions, per "Corrections" in `docs/transcription.md`. Approve the clear grammar mistakes yourself; leave the rest for the owner.
5. **Mark it done** in `PROGRESS.md`: `done: N entries, A corrected automatically, Q questions`.
6. **Stop.** If no chapter is left `todo` or `in progress`, change the line `Status: running` to `Status: ALL DONE`.

**If a chapter can't be finished** for a reason only the owner can fix (a tool fails on it in a way no edit under `content/` fixes, or a page can't be read), set its status to `blocked: <short reason>`, explain under "Notes for the owner" in `PROGRESS.md`, and stop. The next round moves on to the next chapter, so the run never repeats the same failure.

**What a round may do.** Read any file, edit files under `content/`, and run the project's tools as plain commands from the project folder, e.g. `.venv/bin/python tools/zoom.py 96 0.30 0.35`. Write no `cd`, pipes or other shell commands: anything else is refused, because nobody is there to approve it.

Never commit to git, and never change `docs/` or `tools/` during the run. If a rule or a tool seems wrong, describe it under "Notes for the owner" in `PROGRESS.md` and carry on with the rules as they are.
