#!/usr/bin/env python3
"""Clean credits, drop clear non-Romanian names, fetch extra Wikipedia photos."""

from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = "RomanianCast/1.0 (local production casting database; python-urllib)"
ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "src" / "data" / "actors.json"
EN_API = "https://en.wikipedia.org/w/api.php"
RO_API = "https://ro.wikipedia.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"

RO_PLACE = re.compile(
    r"bucure|bucharest|iași|iasi|cluj|timiș|timisoara|constan|brasov|brașov|galați|"
    r"craiova|ploie|brăila|braila|oradea|pitești|pitesti|sibiu|bacău|bacau|"
    r"mureș|mures|baia mare|buzău|buzau|botoșani|botosani|suceava|piatra|"
    r"satu mare|românia|romania|chișinău|chisinau|moldova|basarabia|transil|"
    r"oltenia|muntenia|dobrogea|banat|maramure|arhdeal|arad|alba|hunedoara|"
    r"târgu|targu|făgăraș|fagaras|sîngere|singere|bălți|balti|cahul|"
    r"gala[tț]i|constan[tț]a",
    re.I,
)
RO_DESC = re.compile(r"român|romanian|româno|moldov", re.I)
FOREIGN_DESC = re.compile(
    r"\b(american|britanic|british|french|francez|german(?!ic)|italian|"
    r"spaniol|spanish|rus|russian|canadian|australian|irish|suedez|swedish|"
    r"norvegian|danish|dutch|olandez|japanese|chinez|korean|brazilian|"
    r"mexican|argentin|actor american|actriță american|actrice américaine)\b",
    re.I,
)
QID_TITLE = re.compile(r"^Q\d+$")

EXTRA_NAMES = [
    "Mara Bugarin",
    "Emilia Dobrin",
    "Constantin Cojocaru",
    "Doru Ana",
]


def request(url: str, data: bytes | None = None) -> dict:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": "application/json"},
        method="POST" if data else "GET",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def wiki_thumbs(api: str, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i : i + 40]
        params = {
            "action": "query",
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": "640",
            "titles": "|".join(chunk),
            "format": "json",
            "redirects": "1",
        }
        url = api + "?" + urllib.parse.urlencode(params, safe=":")
        try:
            data = request(url)
        except Exception as exc:  # noqa: BLE001
            print("wiki thumbs failed", exc)
            continue
        redirects = {r["from"]: r["to"] for r in data.get("query", {}).get("redirects", [])}
        pages = data.get("query", {}).get("pages", {})
        by_title = {}
        for page in pages.values():
            title = page.get("title")
            thumb = (page.get("thumbnail") or {}).get("source")
            if title and thumb:
                by_title[title] = thumb
        for original in chunk:
            resolved = redirects.get(original, original)
            if resolved in by_title:
                out[original] = by_title[resolved]
        time.sleep(0.4)
    return out


def is_foreign(actor: dict) -> bool:
    desc = actor.get("description") or ""
    place = actor.get("birthPlace") or ""
    if RO_PLACE.search(place) or RO_DESC.search(desc) or RO_DESC.search(place):
        return False
    if FOREIGN_DESC.search(desc) and not RO_DESC.search(desc):
        return True
    return False


def clean_credits(credits: list[dict]) -> list[dict]:
    best: dict[str, dict] = {}
    for cred in credits:
        title = (cred.get("title") or "").strip()
        if not title or QID_TITLE.match(title):
            continue
        year = cred.get("year")
        if not isinstance(year, int) or year < 2016 or year > 2028:
            continue
        key = title.casefold()
        prev = best.get(key)
        if not prev or year > prev["year"]:
            best[key] = {"title": title, "year": year, "medium": cred.get("medium") or "film"}
    return sorted(best.values(), key=lambda c: (-c["year"], c["title"]))


def fetch_extra_people() -> list[dict]:
    names = " ".join(json.dumps(n) for n in EXTRA_NAMES)
    query = f"""
    SELECT DISTINCT ?person ?personLabel ?personDescription ?image ?gender ?genderLabel
           ?birthDate ?imdb ?tmdb ?placeLabel ?articleRo ?articleEn
    WHERE {{
      VALUES ?name {{ {names} }}
      ?person rdfs:label ?name .
      FILTER(LANG(?name) IN ("en", "ro"))
      ?person wdt:P31 wd:Q5 .
      OPTIONAL {{ ?person wdt:P18 ?image }}
      OPTIONAL {{ ?person wdt:P21 ?gender }}
      OPTIONAL {{ ?person wdt:P569 ?birthDate }}
      OPTIONAL {{ ?person wdt:P345 ?imdb }}
      OPTIONAL {{ ?person wdt:P4985 ?tmdb }}
      OPTIONAL {{ ?person wdt:P19 ?place }}
      OPTIONAL {{
        ?articleRo schema:about ?person ; schema:isPartOf <https://ro.wikipedia.org/> .
      }}
      OPTIONAL {{
        ?articleEn schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ro,en". }}
    }}
    """
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    try:
        data = request(SPARQL, data=body)
    except Exception as exc:  # noqa: BLE001
        print("extra people failed", exc)
        return []
    rows = []
    for b in data["results"]["bindings"]:
        rows.append({k: v.get("value") for k, v in b.items()})
    return rows


def qid(uri: str | None) -> str | None:
    return uri.rsplit("/", 1)[-1] if uri else None


def gender_of(label: str | None) -> str:
    blob = (label or "").lower()
    if "femeie" in blob or "female" in blob:
        return "female"
    if "bărbat" in blob or "barbat" in blob or "male" in blob:
        return "male"
    return "unknown"


def commons_thumb(file_url: str, width: int = 640) -> str:
    sep = "&" if "?" in file_url else "?"
    return f"{file_url}{sep}width={width}"


def main() -> None:
    payload = json.loads(DB.read_text(encoding="utf-8"))
    actors: list[dict] = payload["actors"]
    by_id = {a["id"]: a for a in actors}
    by_name = {a["name"].casefold(): a for a in actors}

    print("Fetching a few missing names from Wikidata…")
    for row in fetch_extra_people():
        pid = qid(row.get("person"))
        name = (row.get("personLabel") or "").strip()
        if not pid or not name or name.startswith("Q"):
            continue
        if pid in by_id or name.casefold() in by_name:
            continue
        actor = {
            "id": pid,
            "name": name,
            "description": (row.get("personDescription") or "").strip(),
            "photo": commons_thumb(row["image"]) if row.get("image") else None,
            "gender": gender_of(row.get("genderLabel")),
            "birthDate": (row.get("birthDate") or "")[:10] or None,
            "deathDate": None,
            "birthPlace": row.get("placeLabel"),
            "heightCm": None,
            "imdbId": row.get("imdb"),
            "tmdbId": row.get("tmdb"),
            "wikipediaRo": row.get("articleRo"),
            "wikipediaEn": row.get("articleEn"),
            "romanian": True,
            "credits": [],
            "recentCreditCount": 0,
            "latestYear": None,
            "media": [],
        }
        actors.append(actor)
        by_id[pid] = actor
        by_name[name.casefold()] = actor
        print("  added", name)

    print("English Wikipedia thumbnails…")
    need = []
    for actor in actors:
        if actor.get("photo"):
            continue
        url = actor.get("wikipediaEn")
        if not url:
            continue
        title = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
        need.append((actor, title))
    thumbs = wiki_thumbs(EN_API, [t for _, t in need])
    added = 0
    for actor, title in need:
        if title in thumbs:
            actor["photo"] = thumbs[title]
            added += 1
    print(f"  attached {added} English Wikipedia photos")

    cleaned = []
    dropped_foreign = 0
    for actor in actors:
        if is_foreign(actor):
            dropped_foreign += 1
            continue
        actor["credits"] = clean_credits(actor.get("credits") or [])
        actor["recentCreditCount"] = len(actor["credits"])
        actor["latestYear"] = actor["credits"][0]["year"] if actor["credits"] else None
        actor["media"] = sorted({c["medium"] for c in actor["credits"]})
        cleaned.append(actor)

    cleaned.sort(key=lambda a: (-a["recentCreditCount"], -(a["latestYear"] or 0), a["name"]))
    payload["actors"] = cleaned
    payload["count"] = len(cleaned)
    payload["withPhoto"] = sum(1 for a in cleaned if a.get("photo"))
    payload["withRecentCredits"] = sum(1 for a in cleaned if a.get("credits"))
    DB.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"Wrote {payload['count']} actors, {payload['withPhoto']} photos, "
        f"{payload['withRecentCredits']} with credits (dropped {dropped_foreign} non-Romanian)"
    )


if __name__ == "__main__":
    main()
