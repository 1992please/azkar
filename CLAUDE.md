# Azkar

- The plan, features and content pipeline are in `README.md`.
- Before any transcription work, read `docs/transcription.md` and follow it exactly. Its first rule: the book is the source of truth, so read every word from zoomed scans and never write a hadith from memory.
- The book's index is `content/book/index.tsv`, and the work units are `content/book/chapters.tsv`. Run `tools/check.py` after every change to a chapter file, and `tools/pipeline.py <chapter>` once a chapter is transcribed.
- The long run follows `docs/long-run.md`; its order and status are in `content/book/PROGRESS.md`.
- Run the tools with `.venv/bin/python` (set up with `python3 -m venv .venv && .venv/bin/pip install -r tools/requirements.txt`). Downloads, page images and review pages live in `.cache/`, which is not in git.
- The owner makes the git commits; don't commit unless asked.
