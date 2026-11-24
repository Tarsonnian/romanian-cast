#!/usr/bin/env python3
"""Retry missing headshots via Wikimedia APIs (no FilePath hotlink; respects thumbnail sizes)."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from io import BytesIO
from pathlib import Path

THUMB_STEPS = (20, 40, 60, 120, 250, 330, 500, 960, 1280, 1920, 3840)
THUMB_PX_RE = re.compile(r"/(\d+)px-")

from PIL import Image, ImageDraw, ImageFont

UA = "RomanianCast/1.0 (local production casting catalog; python-urllib)"
CTX = ssl.create_default_context()
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "src" / "data" / "actors.json"
PHOTO_DIR = ROOT / "public" / "photos"
REPORT = ROOT / "scripts" / "photo-report.json"
CACHE = ROOT / "scripts" / "cache"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"


def request(url: str, retries: int = 6) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 503, 502):
                wait = 12 * (attempt + 1)
                print(f"  HTTP {exc.code}, wait {wait}s")
                time.sleep(wait)
                continue
            return None
        except Exception:
            time.sleep(2 + attempt)
    return None


def get_json(url: str) -> dict | None:
    raw = request(url)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def initials(name: str) -> str:
    parts = [p for p in name.replace("(", " ").replace(")", " ").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def save_image(raw: bytes, dest: Path) -> bool:
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception:
        return False
    if img.width < 60 or img.height < 60:
        return False
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (28, 22, 18))
        rgba = img.convert("RGBA")
        bg.paste(rgba, mask=rgba.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    w, h = img.size
    target = 3 / 4
    if w / h > target:
        new_w = max(1, int(h * target))
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = max(1, int(w / target))
        top = max(0, int((h - new_h) * 0.12))
        if top + new_h > h:
            top = max(0, h - new_h)
        img = img.crop((0, top, w, top + new_h))
    img.thumbnail((360, 480), Image.Resampling.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.jpg")
    img.save(tmp, "JPEG", quality=82, optimize=True)
    if tmp.stat().st_size < 1500:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    return True


def placeholder(name: str, dest: Path) -> None:
    w, h = 360, 480
    img = Image.new("RGB", (w, h), (36, 28, 22))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, w, 6), fill=(201, 148, 48))
    try:
        font = ImageFont.truetype(FONT, 96)
    except OSError:
        font = ImageFont.load_default()
    text = initials(name)
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((w - tw) / 2, (h - th) / 2 - 10), text, font=font, fill=(222, 184, 110))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=85, optimize=True)


def wiki_title(url: str | None) -> str | None:
    if not url:
        return None
    return urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")


def normalize_thumb_url(url: str) -> str:
    """Wikimedia 429s any thumbnail width not in the production step list."""
    m = THUMB_PX_RE.search(url)
    if not m:
        return url
    width = int(m.group(1))
    if width in THUMB_STEPS:
        return url
    step = next((s for s in THUMB_STEPS if s >= width), THUMB_STEPS[-1])
    return url[: m.start(1)] + str(step) + url[m.end(1) :]


def filename_from_p18(url: str) -> str:
    part = url.split("Special:FilePath/")[-1]
    return urllib.parse.unquote(part.split("?")[0])


def cache_p18() -> dict[str, str]:
    out: dict[str, str] = {}
    for name in ("wd_citizens.json", "wd_born.json"):
        path = CACHE / name
        if not path.exists():
            continue
        for row in json.loads(path.read_text(encoding="utf-8")):
            img = row.get("image")
            pid = (row.get("person") or "").rsplit("/", 1)[-1]
            if img and pid:
                out[pid] = filename_from_p18(img)
    return out


def commons_thumbs(filenames: list[str]) -> dict[str, str]:
    """filename -> thumb url via imageinfo (allowed sizes)."""
    mapping: dict[str, str] = {}
    for i in range(0, len(filenames), 40):
        chunk = filenames[i : i + 40]
        titles = "|".join("File:" + f for f in chunk)
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "prop": "imageinfo",
                "iiprop": "url|mime",
                "iiurlwidth": "330",
                "redirects": "1",
                "titles": titles,
            }
        )
        data = get_json("https://commons.wikimedia.org/w/api.php?" + params)
        time.sleep(0.4)
        if not data:
            continue
        for page in data.get("query", {}).get("pages", {}).values():
            title = (page.get("title") or "").replace("File:", "")
            info = (page.get("imageinfo") or [{}])[0]
            url = info.get("thumburl") or info.get("url")
            mime = info.get("mime") or ""
            if url and mime.startswith("image/"):
                mapping[title] = url
        print(f"  commons imageinfo {min(i+40, len(filenames))}/{len(filenames)}")
    return mapping


def wiki_rest_image(lang: str, title: str) -> str | None:
    quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
    data = get_json(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quoted}")
    time.sleep(0.25)
    if not data:
        return None
    for key in ("originalimage", "thumbnail"):
        src = (data.get(key) or {}).get("source")
        if src:
            return src
    return None


def wiki_pageimages(lang: str, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i : i + 40]
        params = urllib.parse.urlencode(
            {
                "action": "query",
                "format": "json",
                "prop": "pageimages",
                "piprop": "thumbnail",
                "pithumbsize": "330",
                "redirects": "1",
                "titles": "|".join(chunk),
            }
        )
        data = get_json(f"https://{lang}.wikipedia.org/w/api.php?" + params)
        time.sleep(0.4)
        if not data:
            continue
        redirects = {r["from"]: r["to"] for r in data.get("query", {}).get("redirects", [])}
        pages = {}
        for page in data.get("query", {}).get("pages", {}).values():
            src = (page.get("thumbnail") or {}).get("source")
            if page.get("title") and src:
                pages[page["title"]] = src
        for original in chunk:
            resolved = redirects.get(original, original)
            if resolved in pages:
                out[original] = pages[resolved]
    return out


def commons_search(name: str) -> str | None:
    last = name.split()[-1] if name.split() else name
    if len(last) < 4:
        return None
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": name,
            "gsrnamespace": "6",
            "gsrlimit": "6",
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": "330",
        }
    )
    data = get_json("https://commons.wikimedia.org/w/api.php?" + params)
    time.sleep(0.35)
    if not data:
        return None
    last_cf = last.casefold()
    first = name.split()[0].casefold()
    ranked = []
    for page in data.get("query", {}).get("pages", {}).values():
        title = (page.get("title") or "").replace("File:", "")
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime") or ""
        url = info.get("thumburl") or info.get("url")
        if not url or not mime.startswith("image/"):
            continue
        tcf = title.casefold()
        if last_cf not in tcf:
            continue
        if any(x in tcf for x in ("flag", "coat of arms", "logo", "map", "icon")):
            continue
        score = 2 if first in tcf else 1
        ranked.append((score, url))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked else None


def download(url: str, dest: Path) -> bool:
    raw = request(normalize_thumb_url(url))
    if not raw:
        return False
    return save_image(raw, dest)


def needs_photo(actor: dict, placeholders: set[str]) -> bool:
    dest = PHOTO_DIR / f"{actor['id']}.jpg"
    if actor["name"] in placeholders:
        return True
    if not dest.exists():
        return True
    return dest.stat().st_size < 8000


def main() -> None:
    print("Cooling off Wikimedia rate limit…")
    time.sleep(20)
    payload = json.loads(DB.read_text(encoding="utf-8"))
    actors = payload["actors"]
    report = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {"placeholders": []}
    placeholders = set(report.get("placeholders") or [])
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)

    p18 = cache_p18()
    todo = [a for a in actors if needs_photo(a, placeholders)]
    print(f"Need photos: {len(todo)} / {len(actors)}")

    # 1) Wikidata P18 via Commons imageinfo
    files = []
    id_to_file = {}
    for a in todo:
        fn = p18.get(a["id"])
        if fn:
            files.append(fn)
            id_to_file[a["id"]] = fn
    print(f"Wikidata P18 files: {len(files)}")
    thumbs = commons_thumbs(sorted(set(files)))
    got = 0
    for a in todo:
        fn = id_to_file.get(a["id"])
        if not fn:
            continue
        url = thumbs.get(fn) or thumbs.get(fn.replace("_", " "))
        if not url:
            continue
        dest = PHOTO_DIR / f"{a['id']}.jpg"
        if download(url, dest):
            got += 1
            placeholders.discard(a["name"])
        time.sleep(0.15)
    print(f"  saved {got} from Wikidata/Commons")

    todo = [a for a in actors if needs_photo(a, placeholders)]
    print(f"Still need: {len(todo)}")

    # 2) Wikipedia pageimages in batches
    for lang, key in (("ro", "wikipediaRo"), ("en", "wikipediaEn")):
        titled = []
        by_title: dict[str, list[dict]] = {}
        for a in todo:
            t = wiki_title(a.get(key))
            if not t:
                continue
            titled.append(t)
            by_title.setdefault(t, []).append(a)
        print(f"Wikipedia {lang} pageimages for {len(titled)} titles")
        found = wiki_pageimages(lang, sorted(set(titled)))
        saved = 0
        for title, url in found.items():
            for a in by_title.get(title, []):
                if not needs_photo(a, placeholders):
                    continue
                if download(url, PHOTO_DIR / f"{a['id']}.jpg"):
                    saved += 1
                    placeholders.discard(a["name"])
                time.sleep(0.12)
        print(f"  saved {saved}")

    todo = [a for a in actors if needs_photo(a, placeholders)]
    print(f"Still need: {len(todo)} — REST summaries")

    # 3) REST summary (catches local wiki files that are not pageimages)
    saved = 0
    for i, a in enumerate(todo, 1):
        dest = PHOTO_DIR / f"{a['id']}.jpg"
        url = None
        ro = wiki_title(a.get("wikipediaRo"))
        en = wiki_title(a.get("wikipediaEn"))
        if ro:
            url = wiki_rest_image("ro", ro)
        if not url and en:
            url = wiki_rest_image("en", en)
        if url and download(url, dest):
            saved += 1
            placeholders.discard(a["name"])
        if i % 40 == 0:
            print(f"  rest {i}/{len(todo)} saved {saved}")
    print(f"  saved {saved} from REST")

    todo = [a for a in actors if needs_photo(a, placeholders)]
    print(f"Still need: {len(todo)} — Commons search")
    saved = 0
    for i, a in enumerate(todo, 1):
        url = commons_search(a["name"])
        if url and download(url, PHOTO_DIR / f"{a['id']}.jpg"):
            saved += 1
            placeholders.discard(a["name"])
        if i % 40 == 0:
            print(f"  search {i}/{len(todo)} saved {saved}")
    print(f"  saved {saved} from Commons search")

    # 4) Placeholders for the rest so every card has an image
    still = []
    for a in actors:
        dest = PHOTO_DIR / f"{a['id']}.jpg"
        if needs_photo(a, placeholders) or not dest.exists():
            placeholder(a["name"], dest)
            still.append(a["name"])
        a["photo"] = f"/photos/{a['id']}.jpg"

    payload["actors"] = actors
    payload["withPhoto"] = len(actors)
    DB.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    real = len(actors) - len(still)
    REPORT.write_text(
        json.dumps(
            {
                "count": len(actors),
                "realPhotos": real,
                "placeholders": sorted(still),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Real photos: {real}  Placeholders: {len(still)}")


if __name__ == "__main__":
    main()
