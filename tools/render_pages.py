"""Download the book PDF (if needed) and render pages to PNG images.

Usage: python tools/render_pages.py FIRST_PAGE LAST_PAGE [--dpi 150] [--strips N]

Page numbers are PDF pages (1-based), which match the printed page numbers
in this book. Images are written to .cache/pages/pNNN.png, or with --strips
to pNNN-K.png: N overlapping horizontal strips, for reading small tashkeel
marks at a higher dpi.
"""

import argparse
import pathlib
import urllib.request

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF_URL = "http://mostafaaladwy.com/upload/books/azkar.pdf"
PDF_PATH = ROOT / ".cache" / "book" / "azkar.pdf"
PAGES_DIR = ROOT / ".cache" / "pages"


def ensure_pdf() -> pathlib.Path:
    if not PDF_PATH.exists():
        PDF_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"Downloading {PDF_URL}")
        urllib.request.urlretrieve(PDF_URL, PDF_PATH)
    return PDF_PATH


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("first", type=int)
    parser.add_argument("last", type=int)
    parser.add_argument("--dpi", type=int, default=150)
    parser.add_argument("--strips", type=int, default=1)
    args = parser.parse_args()

    doc = pymupdf.open(ensure_pdf())
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for n in range(args.first, args.last + 1):
        page = doc[n - 1]
        if args.strips == 1:
            out = PAGES_DIR / f"p{n:03d}.png"
            page.get_pixmap(dpi=args.dpi).save(out)
            print(out.relative_to(ROOT))
            continue
        r = page.rect
        height = r.height / args.strips
        overlap = height * 0.08  # so a line cut at a strip edge appears whole in one strip
        for k in range(args.strips):
            clip = pymupdf.Rect(r.x0, max(r.y0, r.y0 + k * height - overlap),
                                r.x1, min(r.y1, r.y0 + (k + 1) * height + overlap))
            out = PAGES_DIR / f"p{n:03d}-{k + 1}.png"
            page.get_pixmap(dpi=args.dpi, clip=clip).save(out)
            print(out.relative_to(ROOT))


if __name__ == "__main__":
    main()
