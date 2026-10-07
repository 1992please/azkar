"""Arabic text normalization shared by the content tools."""

import re

TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭـ]")
NON_LETTERS = re.compile(r"[^ء-ي\s]")
LETTERS = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي", "ء": "",
})
# Spellings that differ between printed books and the hadith collections.
# "ابن" is written for "بن" when a name wraps to the start of a printed line,
# and "ثنا" is the common abbreviation of "حدثنا".
WORDS = {"ابن": "بن", "ثنا": "حدثنا"}


def expand_salutation(text: str) -> str:
    return text.replace("ﷺ", " صلى الله عليه وسلم ")


def normalize_word(word: str) -> str:
    """Normalize one word; returns "" for punctuation and digits."""
    word = TASHKEEL.sub("", word).translate(LETTERS)
    word = NON_LETTERS.sub("", word)
    return WORDS.get(word, word)


def words(text: str) -> list[str]:
    """Normalized words of a text, for matching."""
    normalized = (normalize_word(w) for w in expand_salutation(text).split())
    return [w for w in normalized if w]
