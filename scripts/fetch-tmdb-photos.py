#!/usr/bin/env python3
"""Fetch TMDB profile photos for every actor and cache local headshots."""

from __future__ import annotations

import json
import os
import re
import ssl
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "src" / "data" / "actors.json"
PHOTO_DIR = ROOT / "public" / "photos"
REPORT = ROOT / "scripts" / "photo-report.json"
ENV = ROOT / ".env"
FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
API = "https://api.themoviedb.org/3"
IMG = "https://image.tmdb.org/t/p/w500"
UA = "RomanianCast/1.0 (internal Substratum Pictures casting catalog)"
CTX = ssl.create_default_context()
ROMANIA = ("romania", "românia", "romanian", "bucharest", "bucurești", "bucuresti", "targoviste")


def load_api_key() -> str:
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TMDB_API_KEY=") and not key:
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not key:
        raise SystemExit("TMDB_API_KEY missing from .env")
    return key


def fold_name(value: str) -> str:
    table = str.maketrans(
        "ăâîșşțţĂÂÎȘŞȚŢáéíóúÁÉÍÓÚ",
        "aaisttAAISTTaeiouAEIOU",
    )
    value = unicodedata.normalize("NFKD", value.translate(table))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9]+", " ", value.casefold())
    return " ".join(value.split())


def names_equal(a: str, b: str) -> bool:
    return fold_name(a) == fold_name(b)


def get(url: str, retries: int = 6) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json,image/*"})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
                if resp.status >= 400:
                    return None
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 502, 503):
                time.sleep(1.5 * (attempt + 1))
                continue
            return None
        except Exception:
            time.sleep(0.8 * (attempt + 1))
    return None


def get_json(url: str) -> dict | None:
    raw = get(url)
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8", errors="replace"))
    except json.JSONDecodeError:
        return None


def api_url(path: str, key: str, **params: str) -> str:
    query = {"api_key": key, **params}
    return f"{API}{path}?{urllib.parse.urlencode(query)}"


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


def looks_placeholder(path: Path) -> bool:
    if not path.exists():
        return True
    if path.stat().st_size < 9000:
        return True
    try:
        img = Image.open(path)
        sample = img.resize((8, 8)).convert("RGB")
        pixels = list(sample.getdata())
        brown = sum(1 for r, g, b in pixels if r < 70 and g < 55 and b < 45)
        gold = sum(1 for r, g, b in pixels if r > 160 and g > 110 and b < 140)
        return brown >= 40 and gold >= 2
    except Exception:
        return True


def credit_tokens(actor: dict) -> set[str]:
    tokens: set[str] = set()
    for credit in actor.get("credits") or []:
        folded = fold_name(credit.get("title") or "")
        if folded:
            tokens.add(folded)
            tokens.update(folded.split())
    return {t for t in tokens if len(t) > 3}


def romanian_context(person: dict) -> bool:
    blob = " ".join(
        [
            person.get("place_of_birth") or "",
            person.get("original_name") or "",
            " ".join(person.get("also_known_as") or []),
            " ".join(
                str(item.get("original_language") or "")
                + " "
                + str(item.get("title") or item.get("name") or "")
                + " "
                + " ".join(item.get("origin_country") or [])
                for item in person.get("known_for") or []
            ),
        ]
    ).casefold()
    return any(hint in blob for hint in ROMANIA)


def score_person(actor: dict, person: dict) -> int:
    person_name = person.get("name") or person.get("original_name") or ""
    if not names_equal(actor["name"], person_name):
        aliases = [person_name, *(person.get("also_known_as") or [])]
        if not any(names_equal(actor["name"], alias) for alias in aliases):
            return 0
    score = 40
    dept = (person.get("known_for_department") or "").casefold()
    if dept in {"acting", "actors"}:
        score += 25
    elif dept:
        score -= 10
    if person.get("profile_path"):
        score += 8
    if romanian_context(person):
        score += 20
    birth = (actor.get("birthDate") or "")[:10]
    pb = (person.get("birthday") or "")[:10]
    if birth and pb:
        if birth == pb:
            score += 40
        elif birth[:4] == pb[:4]:
            score += 22
        else:
            try:
                if abs(int(birth[:4]) - int(pb[:4])) > 8:
                    score -= 25
            except ValueError:
                pass
    gender_map = {1: "female", 2: "male"}
    pg = gender_map.get(person.get("gender") or 0)
    if pg and actor.get("gender") in {"female", "male"}:
        if pg == actor["gender"]:
            score += 8
        else:
            score -= 15
    known = {
        fold_name(item.get("title") or item.get("name") or "")
        for item in person.get("known_for") or []
    }
    known.discard("")
    credits = credit_tokens(actor)
    overlap = known & credits
    score += 18 * len(overlap)
    score += min(12, int(person.get("popularity") or 0) // 4)
    return score


def pick_search_match(actor: dict, results: list[dict]) -> dict | None:
    ranked: list[tuple[int, dict]] = []
    for person in results[:10]:
        score = score_person(actor, person)
        if score >= 55:
            ranked.append((score, person))
    if not ranked:
        return None
    ranked.sort(key=lambda item: item[0], reverse=True)
    best_score, best = ranked[0]
    if len(ranked) > 1 and ranked[1][0] >= best_score - 8:
        # Ambiguous near-tie: only accept a clearly Romanian/acting unique winner.
        if not (romanian_context(best) and (best.get("known_for_department") == "Acting")):
            return None
        if ranked[1][0] == best_score:
            return None
    return best


def person_from_id(person_id: str, key: str) -> dict | None:
    return get_json(api_url(f"/person/{person_id}", key, language="en-US"))


def find_by_imdb(imdb_id: str, key: str) -> dict | None:
    data = get_json(api_url(f"/find/{imdb_id}", key, external_source="imdb_id"))
    people = (data or {}).get("person_results") or []
    return people[0] if people else None


def search_person(name: str, key: str) -> list[dict]:
    data = get_json(api_url("/search/person", key, query=name, include_adult="false", language="en-US"))
    return (data or {}).get("results") or []


def resolve_actor(actor: dict, key: str) -> dict:
    person = None
    source = None
    tmdb_id = actor.get("tmdbId")
    if tmdb_id:
        person = person_from_id(str(tmdb_id), key)
        source = "tmdb-id"
    if person is None and actor.get("imdbId"):
        found = find_by_imdb(actor["imdbId"], key)
        if found:
            person = found
            source = "imdb-find"
            if not found.get("profile_path") and found.get("id"):
                details = person_from_id(str(found["id"]), key)
                if details:
                    person = {**found, **details}
    if person is None:
        results = search_person(actor["name"], key)
        match = pick_search_match(actor, results)
        if match is None and fold_name(actor["name"]) != actor["name"].casefold():
            results = search_person(fold_name(actor["name"]), key)
            match = pick_search_match(actor, results)
        if match:
            person = match
            source = "search"
            if match.get("id") and (actor.get("birthDate") or not match.get("profile_path")):
                details = person_from_id(str(match["id"]), key)
                if details:
                    person = {**match, **details}
                    if score_person(actor, person) < 55:
                        person = None
                        source = None
    profile = (person or {}).get("profile_path")
    pid = (person or {}).get("id")
    return {
        "id": actor["id"],
        "tmdbId": str(pid) if pid else actor.get("tmdbId"),
        "profile_path": profile,
        "source": source if person else None,
        "has_image": bool(profile),
    }


def download_profile(profile_path: str, dest: Path) -> bool:
    raw = get(f"{IMG}{profile_path}")
    if not raw:
        raw = get(f"https://image.tmdb.org/t/p/w185{profile_path}")
    if not raw:
        return False
    return save_image(raw, dest)


def main() -> None:
    key = load_api_key()
    payload = json.loads(DB.read_text(encoding="utf-8"))
    actors = payload["actors"]
    PHOTO_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Resolving TMDB profiles for {len(actors)} actors…")
    resolved: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(resolve_actor, actor, key): actor["id"] for actor in actors}
        done = 0
        for fut in as_completed(futs):
            actor_id = futs[fut]
            done += 1
            try:
                resolved[actor_id] = fut.result()
            except Exception as exc:
                resolved[actor_id] = {
                    "id": actor_id,
                    "tmdbId": None,
                    "profile_path": None,
                    "source": None,
                    "has_image": False,
                    "error": str(exc),
                }
            if done % 80 == 0 or done == len(actors):
                print(f"  resolved {done}/{len(actors)}")

    print("Downloading TMDB stills…")
    tmdb_ok: set[str] = set()
    sources: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        downloads = {}
        for actor in actors:
            info = resolved.get(actor["id"]) or {}
            if info.get("tmdbId"):
                actor["tmdbId"] = str(info["tmdbId"])
            dest = PHOTO_DIR / f"{actor['id']}.jpg"
            profile = info.get("profile_path")
            if profile:
                downloads[pool.submit(download_profile, profile, dest)] = (actor, dest)
        done = 0
        for fut in as_completed(downloads):
            actor, dest = downloads[fut]
            done += 1
            ok = False
            try:
                ok = fut.result()
            except Exception:
                ok = False
            if ok:
                tmdb_ok.add(actor["id"])
                actor["photo"] = f"/photos/{actor['id']}.jpg"
                src = resolved[actor["id"]].get("source") or "tmdb"
                sources[src] = sources.get(src, 0) + 1
            if done % 80 == 0 or done == len(downloads):
                print(f"  downloaded {done}/{len(downloads)}")

    placeholders: list[str] = []
    for actor in actors:
        dest = PHOTO_DIR / f"{actor['id']}.jpg"
        actor["photo"] = f"/photos/{actor['id']}.jpg"
        if actor["id"] in tmdb_ok:
            continue
        if dest.exists() and not looks_placeholder(dest):
            sources["kept-existing"] = sources.get("kept-existing", 0) + 1
            continue
        placeholder(actor["name"], dest)
        placeholders.append(actor["name"])
        sources["placeholder"] = sources.get("placeholder", 0) + 1

    real_tmdb = len(tmdb_ok)
    still_placeholders = placeholders

    payload["actors"] = actors
    payload["count"] = len(actors)
    payload["withPhoto"] = sum(1 for a in actors if (PHOTO_DIR / f"{a['id']}.jpg").exists())
    sources_list = list(payload.get("sources") or [])
    if "TMDB API (attribution required)" not in sources_list:
        sources_list.append("TMDB API (attribution required)")
    payload["sources"] = sources_list
    DB.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    report = {
        "count": len(actors),
        "localPhotos": payload["withPhoto"],
        "tmdbPhotos": real_tmdb,
        "placeholders": sorted(still_placeholders),
        "sources": sources,
        "withTmdbId": sum(1 for a in actors if a.get("tmdbId")),
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Actors: {len(actors)}")
    print(f"TMDB photos: {real_tmdb}")
    print(f"Placeholders: {len(still_placeholders)}")
    print(f"With tmdbId: {report['withTmdbId']}")
    print("Sources:", sources)


if __name__ == "__main__":
    main()
