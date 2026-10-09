"""Run every step for a chapter after its transcription is written.

Usage: python tools/pipeline.py adhan [--offline]

  1. check       the chapter file (stops here if there are errors)
  2. match       each entry to the hadith databases
  3. ocr         the chapter's pages, and cross-check the transcription
                 against it (the flagged words' line crops are stacked in
                 .cache/ocr/flags/<chapter>/sheet-*.png — look at every one)
  4. misprints   correct the certain slips, propose the rest
  5. check       again (the corrections must be valid)
  6. vocalize    and build the review page
"""

import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable


def run(*args: str) -> None:
    print(f"\n$ {' '.join(args)}")
    result = subprocess.run([PY, *args], cwd=ROOT)
    if result.returncode:
        sys.exit(f"Stopped: {args[0]} failed.")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("name")
    parser.add_argument("--offline", action="store_true", help="don't query dorar.net")
    args = parser.parse_args()
    book = json.loads((ROOT / "content" / "book" / f"{args.name}.json").read_text(encoding="utf-8"))
    first, last = book["book_pages"]
    offline = ["--offline"] if args.offline else []

    run("tools/check.py", args.name)
    run("tools/match.py", args.name)
    run("tools/ocr.py", str(first), str(last))
    run("tools/ocr_check.py", args.name, "--crops")
    run("tools/misprints.py", args.name, *offline)
    run("tools/check.py", args.name)
    run("tools/vocalize.py", args.name)
    run("tools/report.py", args.name)
    print(f"\nReview page: file://{ROOT}/.cache/reports/{args.name}.html")


if __name__ == "__main__":
    main()
