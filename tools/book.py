"""Load transcribed book chapters and apply approved corrections."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOK_DIR = ROOT / "content" / "book"


def load_chapter(name: str) -> dict:
    return json.loads((BOOK_DIR / f"{name}.json").read_text(encoding="utf-8"))


def corrected(entry: dict, field: str) -> str:
    """The field's printed value with its approved corrections applied."""
    value = entry[field]
    for c in entry["corrections"]:
        if c["field"] == field and c["status"] == "approved":
            if value.count(c["printed"]) != 1:
                raise ValueError(f"entry {entry['number']}: correction {c['id']} "
                                 f"must match the {field} exactly once")
            value = value.replace(c["printed"], c["corrected"])
    return value
