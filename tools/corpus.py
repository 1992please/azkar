"""All hadith texts as normalized words, for asking "is this wording attested?".

    from corpus import Corpus
    c = Corpus()
    c.count("ثم استاخر عني")     # times the phrase occurs, as normalized words
    c.freq("مكاتلهم")            # times the word occurs

Built once from hadith-api's seven collections plus Musnad Ahmad and Sunan
al-Darimi from Open-Hadith-Data (its other books repeat hadith-api), and
cached in .cache/corpus/.
"""

import collections
import csv
import json
import pathlib
import re

from arabic import words
from fetch_hadith import HADITH_API_COLLECTIONS, hadith_api_path, open_hadith_path

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "corpus"
OPEN_HADITH_ONLY = ["ahmad", "darimi"]


def _texts():
    for name in HADITH_API_COLLECTIONS:
        for h in json.loads(hadith_api_path(name).read_text(encoding="utf-8"))["hadiths"]:
            yield h["text"]
    csv.field_size_limit(10**8)
    for name in OPEN_HADITH_ONLY:
        with open_hadith_path(name).open(encoding="utf-8", newline="") as f:
            for record in csv.reader(f):
                yield record[1]


class Corpus:
    def __init__(self):
        text_path, freq_path = CACHE / "corpus.txt", CACHE / "freq.json"
        if not text_path.exists():
            CACHE.mkdir(parents=True, exist_ok=True)
            lines = (" ".join(words(t)) for t in _texts())
            text_path.write_text("\n".join(l for l in lines if l), encoding="utf-8")
            counts = collections.Counter(text_path.read_text(encoding="utf-8").split())
            freq_path.write_text(json.dumps(counts, ensure_ascii=False), encoding="utf-8")
        # Each hadith is one line; padding with spaces makes every phrase match whole words.
        self.text = " " + text_path.read_text(encoding="utf-8").replace("\n", " \n ") + " "
        self.freqs = json.loads(freq_path.read_text(encoding="utf-8"))

    def count(self, phrase: str) -> int:
        return self.text.count(f" {phrase} ") if phrase else 0

    def freq(self, word: str) -> int:
        return self.freqs.get(word, 0)

    def fill(self, before: list[str], after: list[str]) -> collections.Counter:
        """Words found between the given context words, with counts."""
        pattern = " " + " ".join(map(re.escape, before)) + " (\\S+) " + " ".join(map(re.escape, after)) + " "
        return collections.Counter(re.findall(pattern.replace("  ", " "), self.text))
