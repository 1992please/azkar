"""Render zoomed crops of a book page, for reading small marks and doubtful words.

Usage: python tools/zoom.py PAGE TOP BOTTOM [--left 0.1 --right 0.9] [--dpi N]
       python tools/zoom.py PAGE --crop TOP BOTTOM [LEFT RIGHT] --crop TOP BOTTOM [LEFT RIGHT] ...

TOP/BOTTOM/LEFT/RIGHT are fractions of the page (0 = top/left edge, 1 = bottom/right).
A line is about 0.03 of the page high. Each --crop adds one crop of the same page, so
all the doubtful spots of a page can be rendered in one command. Writes
.cache/pages/zoom-pNNN-TOP-BOTTOM.png (with -LEFT-RIGHT added for a partial width),
named after the edges asked for.

A crop's top and bottom are moved out, at most 0.03 of the page, to the gap between two
lines (the pixel row with the least ink across the page), so a crop doesn't cut through a
line or the marks above it. Edges guessed from a strip often fall inside a line: on
2026-10-14 most crops did, and a madda and a phrase were misread from such crops. The
edges used are printed.

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
STRIP_DPI = 400      # a crop shown below this shows little more than the 220-dpi strips
SNAP = 0.03          # how far (fraction of the page) an edge may move out to reach a gap
INK_DPI = 150        # resolution of the ink count used to find the gaps
INK = bytes(range(128))  # gray levels counted as ink


class Ink:
    """How much ink each pixel row of a page has, to move crop edges to the gaps between lines."""

    def __init__(self, page: pymupdf.Page) -> None:
        pix = page.get_pixmap(dpi=INK_DPI, colorspace=pymupdf.csGRAY)
        data, stride, width = pix.samples, pix.stride, pix.width
        self.rows = [width - len(data[y * stride: y * stride + width].translate(None, INK))
                     for y in range(pix.height)]

    def snap(self, edge: float, step: int) -> float:
        """Move a top (step -1) or bottom (step 1) edge out, at most SNAP, to the row with the
        least ink across the page, the nearest one if several tie. A blank row inside a line,
        such as between a madda and its alif, still has ink elsewhere on the line, so the gap
        between two lines wins."""
        size = len(self.rows)
        pos = min(size - 1, max(0, round(edge * size)))
        lines = [pos + step * k for k in range(int(SNAP * size) + 1) if 0 <= pos + step * k < size]
        best = min(lines, key=lambda line: (self.rows[line], abs(line - pos)))
        return min(edge, best / size) if step < 0 else max(edge, best / size)


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
    ink = Ink(page)
    out_dir = ROOT / ".cache" / "pages"
    out_dir.mkdir(parents=True, exist_ok=True)
    for top, bottom, left, right in crops:
        name = f"zoom-p{args.page:03d}-{top:.2f}-{bottom:.2f}"
        if (left, right) != (0.0, 1.0):
            name += f"-{left:.2f}-{right:.2f}"
        top, bottom = ink.snap(top, -1), ink.snap(bottom, 1)
        clip = pymupdf.Rect(r.x0 + r.width * left, r.y0 + r.height * top,
                            r.x0 + r.width * right, r.y0 + r.height * bottom)
        fit = int(SHOWN_PX * 72 / max(clip.width, clip.height))
        dpi = args.dpi or min(fit, MAX_AUTO_DPI)
        out = out_dir / f"{name}.png"
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        pix.save(out)
        note = f"; shown at about {fit} dpi, crop narrower for more detail" if dpi > fit else ""
        if min(dpi, fit) < STRIP_DPI:
            note += "; this wide crop shows little more than the strips: crop to a few words to read marks"
        print(f"{out.relative_to(ROOT)}  ({pix.width}x{pix.height} px, {dpi} dpi{note};"
              f" top and bottom moved out to the gaps between lines: {top:.3f}-{bottom:.3f})")


if __name__ == "__main__":
    main()
