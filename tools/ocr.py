"""OCR book pages with Tesseract, keeping each word's position on the page.

Usage: python tools/ocr.py FIRST_PAGE LAST_PAGE

Needs Tesseract in .cache/ocr (tools/fetch_ocr.sh). Pages are rendered at
300 dpi to .cache/ocr/pages/pNNN.png and read into .cache/ocr/out/pNNN.tsv
(Tesseract's word table). Pages already done are skipped.
"""

import argparse
import csv
import os
import pathlib
import subprocess

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
OCR = ROOT / ".cache" / "ocr"
PAGES = OCR / "pages"
OUT = OCR / "out"
PDF = ROOT / ".cache" / "book" / "azkar.pdf"
DPI = 300


def page_image(n: int) -> pathlib.Path:
    return PAGES / f"p{n:03d}.png"


def run_tesseract(png: pathlib.Path, out_base: pathlib.Path) -> None:
    env = dict(os.environ,
               LD_LIBRARY_PATH=str(OCR / "root" / "usr" / "lib" / "x86_64-linux-gnu"),
               TESSDATA_PREFIX=str(OCR / "tessdata"))
    subprocess.run([str(OCR / "root" / "usr" / "bin" / "tesseract"), str(png), str(out_base),
                    "-l", "ara", "--psm", "4", "tsv"],
                   env=env, check=True, capture_output=True)


def words(n: int) -> list[dict]:
    """The page's OCR words in reading order, with confidence and pixel box."""
    out = []
    with (OUT / f"p{n:03d}.tsv").open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
            if row["level"] == "5" and row["text"].strip():
                out.append({
                    "page": n, "text": row["text"], "conf": float(row["conf"]),
                    "line": (int(row["block_num"]), int(row["par_num"]), int(row["line_num"])),
                    "box": (int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])),
                })
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=int)
    parser.add_argument("last", type=int)
    args = parser.parse_args()
    PAGES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(PDF)
    for n in range(args.first, args.last + 1):
        if (OUT / f"p{n:03d}.tsv").exists():
            continue
        png = page_image(n)
        if not png.exists():
            doc[n - 1].get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY).save(png)
        run_tesseract(png, OUT / f"p{n:03d}")
        print(f"p. {n}: {len(words(n))} words")


if __name__ == "__main__":
    main()
