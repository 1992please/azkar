"""Search the Dorar hadith encyclopedia (dorar.net) through its public API.

    from dorar import search
    for r in search("ثم استأخر عني غير بعيد"): print(r["source"], r["text"])

Each search returns up to 15 narrations from across the hadith literature,
with the narrator, the scholar who graded it, the source book, page or
number, and the grading. Answers are cached in .cache/dorar/ and live
requests are spaced out, so repeated runs don't load dorar's server.
"""

import hashlib
import html
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "dorar"
API = "https://dorar.net/dorar_api.json?skey="
# dorar's firewall rejects requests without a browser-like identification.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36",
    "Accept": "application/json",
    "Accept-Language": "ar,en;q=0.8",
}
PAUSE = 1.5  # seconds between live requests
_last_request = 0.0

FIELDS = {"الراوي": "narrator", "المحدث": "scholar", "المصدر": "source",
          "الصفحة أو الرقم": "reference", "خلاصة حكم المحدث": "grading"}


def _clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def parse(result_html: str) -> list[dict]:
    out = []
    for block in result_html.split('<div class="hadith"')[1:]:
        text_part, _, rest = block.partition("</div>")
        text = _clean(text_part.split(">", 1)[1])
        text = re.sub(r"^\d+\s*-\s*", "", text)
        item = {"text": text}
        info = rest.split('<div class="hadith-info">', 1)[-1].split("</div>", 1)[0]
        for label, value in re.findall(r'info-subtitle">([^<:]+):</span>(.*?)(?=<span class="info-subtitle"|$)', info, re.S):
            key = FIELDS.get(label.strip())
            if key:
                item[key] = _clean(value)
        out.append(item)
    return out


def search(query: str) -> list[dict]:
    global _last_request
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha1(query.encode("utf-8")).hexdigest() + ".json")
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
    else:
        wait = PAUSE - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        request = urllib.request.Request(API + urllib.parse.quote(query), headers=HEADERS)
        with urllib.request.urlopen(request, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
        _last_request = time.time()
        data["query"] = query
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return parse(data.get("ahadith", {}).get("result", ""))
