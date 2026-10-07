"""Download the vocalized Arabic hadith collections used for matching.

Usage: python tools/fetch_hadith.py

Two sources, each skipped if already downloaded:
- fawazahmed0/hadith-api (public domain, Unlicense): the main source. Uses the
  standard hadith numbering, but some hadith are missing (e.g. 203 in Muslim).
- mhashim6/Open-Hadith-Data (ODbL / DbCL): fills those gaps and adds Musnad
  Ahmad and Sunan al-Darimi. Uses its own numbering, not the standard one.
"""

import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
HADITH_API_DIR = ROOT / ".cache" / "hadith-api"
OPEN_HADITH_DIR = ROOT / ".cache" / "open-hadith-data"

HADITH_API_URL = "https://cdn.jsdelivr.net/gh/fawazahmed0/hadith-api@1/editions/ara-{}.min.json"
HADITH_API_COLLECTIONS = ["bukhari", "muslim", "abudawud", "tirmidhi", "nasai", "ibnmajah", "malik"]

OPEN_HADITH_URL = "https://raw.githubusercontent.com/mhashim6/Open-Hadith-Data/master/"
OPEN_HADITH_FILES = {
    "bukhari": "Sahih_Al-Bukhari/sahih_al-bukhari_ahadith_mushakkala_mufassala.utf8.csv",
    "muslim": "Sahih_Muslim/sahih_muslim_ahadith_mushakkala_mufassala.utf8.csv",
    "abudawud": "Sunan_Abu-Dawud/sunan_abu-dawud_ahadith_mushakkala_mufassala.utf8.csv",
    "tirmidhi": "Sunan_Al-Tirmidhi/sunan_al-tirmidhi_ahadith_mushakkala_mufassala.utf8.csv",
    "nasai": "Sunan_Al-Nasai/sunan_al-nasai_ahadith_mushakkala_mufassala.utf8.csv",
    "ibnmajah": "Sunan_Ibn-Maja/sunan_ibn-maja_ahadith_mushakkala_mufassala.utf8.csv",
    "malik": "Maliks_Muwataa/maliks_muwataa_ahadith_mushakkala_mufassala.utf8.csv",
    "ahmad": "Musnad_Ahmad_Ibn-Hanbal/musnad_ahmad_ibn-hanbal_ahadith_mushakkala.utf8.csv",
    "darimi": "Sunan_Al-Darimi/sunan_al-darimi_ahadith_mushakkala_mufassala.utf8.csv",
}


def hadith_api_path(name: str) -> pathlib.Path:
    return HADITH_API_DIR / f"ara-{name}.json"


def open_hadith_path(name: str) -> pathlib.Path:
    return OPEN_HADITH_DIR / f"{name}.csv"


def download(url: str, out: pathlib.Path) -> None:
    if out.exists():
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url}")
    urllib.request.urlretrieve(url, out)


def main() -> None:
    for name in HADITH_API_COLLECTIONS:
        download(HADITH_API_URL.format(name), hadith_api_path(name))
    for name, path in OPEN_HADITH_FILES.items():
        download(OPEN_HADITH_URL + path, open_hadith_path(name))


if __name__ == "__main__":
    main()
