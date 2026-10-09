"""Render a zoomed crop of a book page, for reading small marks and doubtful words.

Usage: python tools/zoom.py PAGE TOP BOTTOM [--left 0.1 --right 0.9] [--dpi 400]

TOP/BOTTOM/LEFT/RIGHT are fractions of the page (0 = top/left edge, 1 = bottom/right).
A line is about 0.03 of the page high. Writes .cache/pages/zoom-pNNN-TOP-BOTTOM.png.
For a word the OCR cross-check flagged, the crops in .cache/ocr/flags/ are usually enough.
"""

import argparse
import pathlib

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF = ROOT / ".cache" / "book" / "azkar.pdf"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=int)
    parser.add_argument("top", type=float)
    parser.add_argument("bottom", type=float)
    parser.add_argument("--left", type=float, default=0.0)
    parser.add_argument("--right", type=float, default=1.0)
    parser.add_argument("--dpi", type=int, default=400)
    args = parser.parse_args()
    page = pymupdf.open(PDF)[args.page - 1]
    r = page.rect
    clip = pymupdf.Rect(r.x0 + r.width * args.left, r.y0 + r.height * args.top,
                        r.x0 + r.width * args.right, r.y0 + r.height * args.bottom)
    out = ROOT / ".cache" / "pages" / f"zoom-p{args.page:03d}-{args.top:.2f}-{args.bottom:.2f}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    page.get_pixmap(dpi=args.dpi, clip=clip).save(out)
    print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
