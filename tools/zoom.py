"""Render zoomed crops of a book page, for reading small marks and doubtful words.

Usage: python tools/zoom.py PAGE TOP BOTTOM [--left 0.1 --right 0.9] [--dpi N]
       python tools/zoom.py PAGE --crop TOP BOTTOM [LEFT RIGHT] --crop TOP BOTTOM [LEFT RIGHT] ...

TOP/BOTTOM/LEFT/RIGHT are fractions of the page (0 = top/left edge, 1 = bottom/right).
A line is about 0.03 of the page high. Each --crop adds one crop of the same page, so
all the doubtful spots of a page can be rendered in one command. Writes
.cache/pages/zoom-pNNN-TOP-BOTTOM.png (with -LEFT-RIGHT added for a partial width).

The Read tool scales an image down to at most 2000 px on its longer side, so by default
a crop is rendered at the highest dpi that fits (up to 1600). A higher --dpi on a wide
crop shows nothing more: crop narrower to see finer detail. The scan itself is 300 dpi.
For a word the OCR cross-check flagged, the crops in .cache/ocr/flags/ are usually enough.
"""

import argparse
import pathlib

import pymupdf

ROOT = pathlib.Path(__file__).resolve().parent.parent
PDF = ROOT / ".cache" / "book" / "azkar.pdf"
SHOWN_PX = 2000      # longest side of an image as the Read tool shows it
MAX_AUTO_DPI = 1600


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=int)
    parser.add_argument("top", type=float, nargs="?")
    parser.add_argument("bottom", type=float, nargs="?")
    parser.add_argument("--left", type=float, default=0.0)
    parser.add_argument("--right", type=float, default=1.0)
    parser.add_argument("--crop", type=float, nargs="+", action="append", default=[], metavar="F",
                        help="TOP BOTTOM [LEFT RIGHT] of one crop; repeat --crop for each further crop")
    parser.add_argument("--dpi", type=int, help="default: the highest the Read tool shows in full")
    args = parser.parse_args()

    crops = []
    if args.top is not None:
        if args.bottom is None:
            parser.error("TOP needs a BOTTOM")
        crops.append((args.top, args.bottom, args.left, args.right))
    for c in args.crop:
        if len(c) not in (2, 4):
            parser.error("--crop takes TOP BOTTOM or TOP BOTTOM LEFT RIGHT")
        crops.append((c[0], c[1], 0.0, 1.0) if len(c) == 2 else tuple(c))
    if not crops:
        parser.error("give TOP BOTTOM or at least one --crop")
    for top, bottom, left, right in crops:
        if not (0 <= top < bottom <= 1 and 0 <= left < right <= 1):
            parser.error(f"bad crop {top} {bottom} {left} {right}: need 0 <= TOP < BOTTOM <= 1, 0 <= LEFT < RIGHT <= 1")

    page = pymupdf.open(PDF)[args.page - 1]
    r = page.rect
    out_dir = ROOT / ".cache" / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    for top, bottom, left, right in crops:
        clip = pymupdf.Rect(r.x0 + r.width * left, r.y0 + r.height * top,
                            r.x0 + r.width * right, r.y0 + r.height * bottom)
        fit = int(SHOWN_PX * 72 / max(clip.width, clip.height))
        dpi = args.dpi or min(fit, MAX_AUTO_DPI)
        name = f"zoom-p{args.page:03d}-{top:.2f}-{bottom:.2f}"
        if (left, right) != (0.0, 1.0):
            name += f"-{left:.2f}-{right:.2f}"
        out = out_dir / f"{name}.png"
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        pix.save(out)
        note = f"; shown at about {fit} dpi, crop narrower for more detail" if dpi > fit else ""
        print(f"{out.relative_to(ROOT)}  ({pix.width}x{pix.height} px, {dpi} dpi{note})")


if __name__ == "__main__":
    main()
