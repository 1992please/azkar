"""Load transcribed book chapters and apply approved corrections."""

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BOOK_DIR = ROOT / "content" / "book"


def load_chapter(name: str) -> dict:
    return json.loads((BOOK_DIR / f"{name}.json").read_text(encoding="utf-8"))


def field_value(entry: dict, field: str):
    """A correction's field: "text", "heading", "takhrij" …, or "footnotes.N" for the N-th footnote (from 0)."""
    if field.startswith("footnotes."):
        notes, k = entry.get("footnotes") or [], field.split(".", 1)[1]
        return notes[int(k)] if k.isdigit() and int(k) < len(notes) else None
    return entry.get(field)


def corrected(entry: dict, field: str) -> str:
    """The field's printed value with its approved corrections applied."""
    value = field_value(entry, field)
    for c in entry["corrections"]:
        if c["field"] == field and c["status"] == "approved":
            if value.count(c["printed"]) != 1:
                raise ValueError(f"entry {entry['number']}: correction {c['id']} "
                                 f"must match the {field} exactly once")
            value = value.replace(c["printed"], c["corrected"])
    return value
