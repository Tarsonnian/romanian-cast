#!/usr/bin/env python3
"""Download and normalize headshots for every actor in the CAST database."""

from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

UA = "RomanianCast/1.0 (local production casting catalog; python)"
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CTX = ssl.create_default_context()
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "src" / "data" / "actors.json"
PHOTO_DIR = ROOT / "public" / "photos"
REPORT = ROOT / "scripts" / "photo-report.json"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"

OG_IMAGE = re.compile(
    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
    re.I,
)
OG_IMAGE_REV = re.compile(
    r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
    re.I,
)
SKIP_IMG = re.compile(
    r"nopicture|no_picture|placeholder|imdb_logo|default_profile|wiki/File:Question|"
    r"flag_of|coat_of_arms|commons-logo|wikimedia-button|ambox",
    re.I,
)


def get(url: str, ua: str = UA, timeout: int = 25) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=timeout) as resp:
            if resp.status >= 400:
                return None
            return resp.read()
    except Exception:
        return None


def get_json(url: str) -> dict | None:
    raw = get(url)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def wiki_title(url: str | None) -> str | None:
    if not url:
        return None
    return urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")


def last_name(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.replace("-", " ")) if p and not p.startswith("(")]
    return parts[-1] if parts else name


def initials(name: str) -> str:
    parts = [p for p in re.split(r"\s+", name.replace("(", " ").replace(")", " ")) if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def looks_like_photo(url: str | None) -> bool:
    if not url:
        return False
    if SKIP_IMG.search(url):
        return False
    return True


def save_image(raw: bytes, dest: Path) -> bool:
    try:
        img = Image.open(BytesIO(raw))
        img.load()
    except Exception:
        return False
    if img.width < 80 or img.height < 80:
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
    img.save(dest, "JPEG", quality=82, optimize=True)
    return dest.exists() and dest.stat().st_size > 1200


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


def wiki_summary_image(lang: str, title: str) -> str | None:
    quoted = urllib.parse.quote(title.replace(" ", "_"), safe="")
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quoted}"
    data = get_json(url)
    if not data:
        return None
    for key in ("originalimage", "thumbnail"):
        src = (data.get(key) or {}).get("source")
        if looks_like_photo(src):
            return src
    return None


def wiki_og_image(article_url: str) -> str | None:
    raw = get(article_url)
    if not raw:
        return None
    html = raw.decode("utf-8", errors="ignore")
    m = OG_IMAGE.search(html) or OG_IMAGE_REV.search(html)
    if not m:
        return None
    src = html_unescape(m.group(1))
    return src if looks_like_photo(src) else None


def html_unescape(s: str) -> str:
    return (
        s.replace("&amp;", "&")
        .replace("&#x3D;", "=")
        .replace("&quot;", '"')
    )


def commons_image(name: str) -> str | None:
    last = last_name(name)
    if len(last) < 3:
        return None
    query = urllib.parse.urlencode(
        {
            "action": "query",
            "format": "json",
            "generator": "search",
            "gsrsearch": f'"{name}" OR "{last}" portrait OR actor OR actriță',
            "gsrnamespace": "6",
            "gsrlimit": "8",
            "prop": "imageinfo",
            "iiprop": "url|mime|size",
            "iiurlwidth": "640",
        }
    )
    data = get_json("https://commons.wikimedia.org/w/api.php?" + query)
    pages = (data or {}).get("query", {}).get("pages", {})
    last_cf = last.casefold()
    first = name.split()[0].casefold() if name.split() else ""
    ranked = []
    for page in pages.values():
        title = (page.get("title") or "").replace("File:", "")
        info = (page.get("imageinfo") or [{}])[0]
        mime = info.get("mime") or ""
        if not mime.startswith("image/"):
            continue
        url = info.get("thumburl") or info.get("url")
        if not looks_like_photo(url) and not looks_like_photo(title):
            continue
        tcf = title.casefold()
        if last_cf not in tcf:
            continue
        score = 2 if first and first in tcf else 1
        ranked.append((score, url))
    ranked.sort(reverse=True)
    return ranked[0][1] if ranked else None


def page_og_image(url: str) -> str | None:
    raw = get(url, ua=BROWSER_UA)
    if not raw:
        return None
    html = raw.decode("utf-8", errors="ignore")
    m = OG_IMAGE.search(html) or OG_IMAGE_REV.search(html)
    if not m:
        return None
    src = html_unescape(m.group(1))
    return src if looks_like_photo(src) else None


def download(url: str, dest: Path) -> bool:
    raw = get(url, ua=BROWSER_UA if "imdb" in url or "media-amazon" in url or "themoviedb" in url else UA)
    if not raw:
        raw = get(url)
    if not raw:
        return False
    return save_image(raw, dest)


def find_remote_url(actor: dict) -> tuple[str | None, str]:
    name = actor["name"]
    en_title = wiki_title(actor.get("wikipediaEn"))
    ro_title = wiki_title(actor.get("wikipediaRo"))
    if en_title:
        url = wiki_summary_image("en", en_title)
        if url:
            return url, "wikipedia-en"
    if ro_title:
        url = wiki_summary_image("ro", ro_title)
        if url:
            return url, "wikipedia-ro"
    if actor.get("wikipediaEn"):
        url = wiki_og_image(actor["wikipediaEn"])
        if url:
            return url, "wikipedia-en-og"
    if actor.get("wikipediaRo"):
        url = wiki_og_image(actor["wikipediaRo"])
        if url:
            return url, "wikipedia-ro-og"
    url = commons_image(name)
    if url:
        return url, "commons"
    if actor.get("imdbId"):
        url = page_og_image(f"https://www.imdb.com/name/{actor['imdbId']}/")
        if url:
            return url, "imdb"
    if actor.get("tmdbId"):
        url = page_og_image(f"https://www.themoviedb.org/person/{actor['tmdbId']}")
        if url:
            return url, "tmdb"
    if actor.get("photo") and looks_like_photo(actor["photo"]):
        return actor["photo"], "existing"
    return None, "placeholder"


def process_actor(actor: dict) -> dict:
    dest = PHOTO_DIR / f"{actor['id']}.jpg"
    source = "cached"
    if dest.exists() and dest.stat().st_size > 1200:
        return {"id": actor["id"], "name": actor["name"], "source": source, "ok": True}
    url, source = find_remote_url(actor)
    ok = False
    if url:
        ok = download(url, dest)
        if not ok:
            source = "placeholder"
    if not ok:
        placeholder(actor["name"], dest)
        source = "placeholder"
        ok = dest.exists()
    return {"id": actor["id"], "name": actor["name"], "source": source, "ok": ok}


def main() -> None:
    payload = json.loads(DB.read_text(encoding="utf-8"))
    actors = payload["actors"]
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    # Existing Wikimedia URLs first — cheap and already known-good.
    known, missing = [], []
    for actor in actors:
        dest = PHOTO_DIR / f"{actor['id']}.jpg"
        if dest.exists() and dest.stat().st_size > 1200:
            results.append({"id": actor["id"], "name": actor["name"], "source": "cached", "ok": True})
            continue
        if actor.get("photo") and looks_like_photo(actor["photo"]):
            known.append(actor)
        else:
            missing.append(actor)

    print(f"Already local: {len(results)}")
    print(f"Downloading existing URLs: {len(known)}")
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(download, a["photo"], PHOTO_DIR / f"{a['id']}.jpg"): a for a in known}
        for i, fut in enumerate(as_completed(futs), 1):
            actor = futs[fut]
            ok = False
            try:
                ok = fut.result()
            except Exception:
                ok = False
            if not ok:
                missing.append(actor)
                continue
            results.append({"id": actor["id"], "name": actor["name"], "source": "existing", "ok": True})
            if i % 40 == 0:
                print(f"  {i}/{len(known)}")

    print(f"Searching public pages for {len(missing)} actors…")
    # Sequential-ish with a few workers: Wikipedia/IMDb rate-limit aggressively.
    with ThreadPoolExecutor(max_workers=3) as pool:
        futs = {pool.submit(process_actor, a): a for a in missing}
        done = 0
        for fut in as_completed(futs):
            done += 1
            try:
                results.append(fut.result())
            except Exception as exc:
                actor = futs[fut]
                placeholder(actor["name"], PHOTO_DIR / f"{actor['id']}.jpg")
                results.append(
                    {"id": actor["id"], "name": actor["name"], "source": "placeholder", "ok": True, "error": str(exc)}
                )
            if done % 25 == 0:
                print(f"  {done}/{len(missing)}")
            time.sleep(0.05)

    by_id = {r["id"]: r for r in results}
    placeholders = []
    for actor in actors:
        dest = PHOTO_DIR / f"{actor['id']}.jpg"
        if not dest.exists():
            placeholder(actor["name"], dest)
            by_id[actor["id"]] = {"id": actor["id"], "name": actor["name"], "source": "placeholder", "ok": True}
        actor["photo"] = f"/photos/{actor['id']}.jpg"
        if by_id.get(actor["id"], {}).get("source") == "placeholder":
            placeholders.append(actor["name"])

    payload["actors"] = actors
    payload["withPhoto"] = sum(1 for a in actors if (PHOTO_DIR / f"{a['id']}.jpg").exists())
    DB.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    sources: dict[str, int] = {}
    for r in by_id.values():
        sources[r.get("source", "unknown")] = sources.get(r.get("source", "unknown"), 0) + 1
    report = {
        "count": len(actors),
        "localPhotos": payload["withPhoto"],
        "sources": sources,
        "placeholders": sorted(placeholders),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Sources:", sources)
    print(f"Placeholders: {len(placeholders)}")
    print(f"Wrote {payload['withPhoto']} local photos")


if __name__ == "__main__":
    main()
