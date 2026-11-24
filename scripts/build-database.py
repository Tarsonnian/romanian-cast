#!/usr/bin/env python3
"""Build a local Romanian screen-actors database from Wikidata + Wikipedia.

Sources are public (CC0 Wikidata, CC BY-SA Wikipedia/Wikimedia). Photos are
stored as Wikimedia/Wikipedia thumbnail URLs so the app can run without an API key.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

UA = "RomanianCast/1.0 (local production casting database; python-urllib)"
SPARQL = "https://query.wikidata.org/sparql"
RO_API = "https://ro.wikipedia.org/w/api.php"
EN_API = "https://en.wikipedia.org/w/api.php"
CTX = ssl.create_default_context()
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "src" / "data" / "actors.json"
CACHE = ROOT / "scripts" / "cache"

OCCUPATIONS = {
    "Q33999": "actor",
    "Q10800557": "film actor",
    "Q10798782": "television actor",
    "Q2405480": "voice actor",
    "Q21199168": "film actress",
    "Q2259451": "stage actor",
}

MEDIUM = {
    "Q11424": "film",
    "Q219126": "film",  # miniseries sometimes typed oddly
    "Q24862": "short",
    "Q226730": "short",  # silent? skip later
    "Q5398426": "tv",
    "Q21191270": "tv",  # TV series episode
    "Q15416": "tv",
    "Q506240": "tv",  # television film
    "Q1259759": "tv",  # television serial
    "Q1366112": "tv",  # miniseries
    "Q374540": "tv",  # web series? telenovela Q23745
    "Q23745": "tv",
    "Q202866": "tv",  # soap
}

RO_CATEGORIES = [
    "Categorie:Actori români",
    "Categorie:Actrițe române",
    "Categorie:Actori de film români",
    "Categorie:Actrițe de film din România",
    "Categorie:Actori de televiziune români",
]


def cache_path(key: str) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    safe = "".join(ch if ch.isalnum() else "_" for ch in key)[:180]
    return CACHE / f"{safe}.json"


def load_cache(key: str):
    path = cache_path(key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return None


def save_cache(key: str, payload) -> None:
    cache_path(key).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def request(url: str, data: bytes | None = None, accept: str = "application/json") -> dict | list:
    req = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": UA, "Accept": accept},
        method="POST" if data else "GET",
    )
    last_err: Exception | None = None
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, context=CTX, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_err = exc
            if exc.code in (429, 500, 502, 503, 504):
                wait = 8 * (attempt + 1)
                retry_after = exc.headers.get("Retry-After") if exc.headers else None
                if retry_after and retry_after.isdigit():
                    wait = max(wait, int(retry_after))
                print(f"  HTTP {exc.code}, waiting {wait}s…")
                time.sleep(wait)
                continue
            raise
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Request failed: {last_err}")


def get(url: str, params: dict) -> dict:
    full = url + "?" + urllib.parse.urlencode(params, safe=":")
    return request(full)


def sparql(query: str, cache_key: str | None = None) -> list[dict]:
    if cache_key:
        cached = load_cache(cache_key)
        if cached is not None:
            print(f"  cache hit: {cache_key}")
            return cached
    body = urllib.parse.urlencode({"query": query, "format": "json"}).encode()
    data = request(SPARQL, data=body)
    rows = []
    for b in data["results"]["bindings"]:
        rows.append({k: v.get("value") for k, v in b.items()})
    if cache_key:
        save_cache(cache_key, rows)
    return rows


def qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def year_of(iso: str | None) -> int | None:
    if not iso:
        return None
    try:
        return int(iso[:4])
    except ValueError:
        return None


def commons_thumb(file_url: str, width: int = 640) -> str:
    # Wikidata P18 already points at Special:FilePath/...
    if "Special:FilePath" in file_url:
        sep = "&" if "?" in file_url else "?"
        return f"{file_url}{sep}width={width}"
    name = urllib.parse.unquote(file_url.rsplit("/", 1)[-1])
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(name)}?width={width}"


def gender_of(label: str | None, uri: str | None) -> str:
    blob = f"{label or ''} {uri or ''}".lower()
    if "q6581072" in blob or "female" in blob or "feminin" in blob or "femeie" in blob:
        return "female"
    if "q6581097" in blob or "male" in blob or "masculin" in blob or "bărbat" in blob or "barbat" in blob:
        return "male"
    if "non-binary" in blob or "nonbinary" in blob or "q48270" in blob:
        return "nonbinary"
    return "unknown"


def fetch_wikidata_people() -> list[dict]:
    print("Wikidata: Romanian actors…")
    query = """
    SELECT DISTINCT ?person ?personLabel ?personDescription ?image ?gender ?genderLabel
           ?birthDate ?deathDate ?imdb ?tmdb ?height ?placeLabel ?articleRo ?articleEn
    WHERE {
      ?person wdt:P31 wd:Q5 .
      ?person wdt:P27 wd:Q218 .
      ?person wdt:P106 ?occ .
      FILTER(?occ IN (wd:Q33999, wd:Q10800557, wd:Q10798782, wd:Q2405480, wd:Q21199168, wd:Q2259451))
      OPTIONAL { ?person wdt:P18 ?image }
      OPTIONAL { ?person wdt:P21 ?gender }
      OPTIONAL { ?person wdt:P569 ?birthDate }
      OPTIONAL { ?person wdt:P570 ?deathDate }
      OPTIONAL { ?person wdt:P345 ?imdb }
      OPTIONAL { ?person wdt:P4985 ?tmdb }
      OPTIONAL { ?person wdt:P2048 ?height }
      OPTIONAL { ?person wdt:P19 ?place }
      OPTIONAL {
        ?articleRo schema:about ?person ; schema:isPartOf <https://ro.wikipedia.org/> .
      }
      OPTIONAL {
        ?articleEn schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "ro,en". }
    }
    """
    rows = sparql(query, cache_key="wd_citizens")
    print(f"  {len(rows)} people")
    return rows


def fetch_born_in_romania_actors() -> list[dict]:
    print("Wikidata: actors born in Romania (catch diaspora)…")
    query = """
    SELECT DISTINCT ?person ?personLabel ?personDescription ?image ?gender ?genderLabel
           ?birthDate ?deathDate ?imdb ?tmdb ?height ?placeLabel ?articleRo ?articleEn
    WHERE {
      ?person wdt:P31 wd:Q5 .
      ?person wdt:P19/wdt:P131* wd:Q218 .
      ?person wdt:P106 ?occ .
      FILTER(?occ IN (wd:Q33999, wd:Q10800557, wd:Q10798782, wd:Q2405480, wd:Q21199168))
      OPTIONAL { ?person wdt:P18 ?image }
      OPTIONAL { ?person wdt:P21 ?gender }
      OPTIONAL { ?person wdt:P569 ?birthDate }
      OPTIONAL { ?person wdt:P570 ?deathDate }
      OPTIONAL { ?person wdt:P345 ?imdb }
      OPTIONAL { ?person wdt:P4985 ?tmdb }
      OPTIONAL { ?person wdt:P2048 ?height }
      OPTIONAL { ?person wdt:P19 ?place }
      OPTIONAL {
        ?articleRo schema:about ?person ; schema:isPartOf <https://ro.wikipedia.org/> .
      }
      OPTIONAL {
        ?articleEn schema:about ?person ; schema:isPartOf <https://en.wikipedia.org/> .
      }
      SERVICE wikibase:label { bd:serviceParam wikibase:language "ro,en". }
    }
    """
    rows = sparql(query, cache_key="wd_born")
    print(f"  {len(rows)} people")
    return rows


def fetch_credits() -> list[dict]:
    print("Wikidata: credits in Romanian film/TV/shorts 2016–2026…")
    all_rows: list[dict] = []
    windows = [(2016, 2018), (2019, 2021), (2022, 2024), (2025, 2026)]
    for start, end in windows:
        query = f"""
        SELECT DISTINCT ?person ?work ?workLabel ?date ?kind
        WHERE {{
          VALUES ?kind {{ wd:Q11424 wd:Q24862 wd:Q5398426 wd:Q506240 wd:Q1366112 wd:Q23745 }}
          ?work wdt:P31 ?kind .
          {{ ?work wdt:P495 wd:Q218 }} UNION {{ ?work wdt:P364 wd:Q7913 }}
          ?work wdt:P577 ?date .
          FILTER(YEAR(?date) >= {start} && YEAR(?date) <= {end})
          ?work wdt:P161 ?person .
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ro,en". }}
        }}
        """
        rows = sparql(query, cache_key=f"wd_credits_{start}_{end}")
        print(f"  {start}–{end}: {len(rows)} cast credits")
        all_rows.extend(rows)
        time.sleep(1)
    return all_rows


def fetch_person_credits(ids: list[str]) -> list[dict]:
    """Recent credits for known actors, including work abroad."""
    print("Wikidata: recent credits for known actors…")
    all_rows: list[dict] = []
    chunk_size = 80
    for i in range(0, len(ids), chunk_size):
        chunk = " ".join(f"wd:{x}" for x in ids[i : i + chunk_size])
        query = f"""
        SELECT DISTINCT ?person ?work ?workLabel ?date ?kind
        WHERE {{
          VALUES ?person {{ {chunk} }}
          VALUES ?kind {{ wd:Q11424 wd:Q24862 wd:Q5398426 wd:Q506240 wd:Q1366112 wd:Q23745 }}
          ?work wdt:P31 ?kind ;
                wdt:P161 ?person ;
                wdt:P577 ?date .
          FILTER(YEAR(?date) >= 2016)
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "ro,en". }}
        }}
        """
        try:
            rows = sparql(query, cache_key=f"wd_person_credits_{i}")
            all_rows.extend(rows)
            print(f"  chunk {i // chunk_size + 1}: {len(rows)}")
        except Exception as exc:  # noqa: BLE001
            print(f"  chunk {i // chunk_size + 1} failed: {exc}")
        time.sleep(0.6)
    return all_rows


def wikipedia_category_members(api: str, titles: list[str]) -> list[str]:
    pages: list[str] = []
    seen_cats: set[str] = set()
    queue = list(titles)
    while queue:
        cat = queue.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        cont = None
        while True:
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": cat,
                "cmlimit": "500",
                "format": "json",
            }
            if cont:
                params["cmcontinue"] = cont
            data = get(api, params)
            for m in data.get("query", {}).get("categorymembers", []):
                title = m.get("title") or ""
                ns = m.get("ns")
                if ns == 14 and title:
                    # stay inside actor-related subcats
                    low = title.lower()
                    if any(k in low for k in ("actor", "actri", "film", "televizi", "secol")):
                        queue.append(title)
                elif ns == 0 and title and not title.startswith("Listă") and not title.startswith("List of"):
                    pages.append(title)
            cont = data.get("continue", {}).get("cmcontinue")
            if not cont:
                break
        time.sleep(0.8)
    return sorted(set(pages))


def wikipedia_pages_meta(api: str, titles: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(titles), 40):
        chunk = titles[i : i + 40]
        params = {
            "action": "query",
            "prop": "pageprops|pageimages|extracts|info",
            "ppprop": "wikibase_item",
            "piprop": "thumbnail",
            "pithumbsize": "640",
            "exintro": "1",
            "explaintext": "1",
            "exchars": "450",
            "inprop": "url",
            "titles": "|".join(chunk),
            "format": "json",
            "redirects": "1",
        }
        data = get(api, params)
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            if page.get("missing") or int(page.get("pageid", 0) or 0) < 0:
                continue
            title = page.get("title")
            if not title:
                continue
            out[title] = {
                "title": title,
                "qid": (page.get("pageprops") or {}).get("wikibase_item"),
                "extract": (page.get("extract") or "").strip(),
                "thumb": ((page.get("thumbnail") or {}).get("source")),
                "url": page.get("fullurl"),
            }
        time.sleep(0.6)
    return out


def merge_person(store: dict[str, dict], row: dict, romanian: bool = False) -> None:
    pid = qid(row.get("person"))
    if not pid or not pid.startswith("Q"):
        return
    rec = store.setdefault(
        pid,
        {
            "id": pid,
            "name": "",
            "description": "",
            "photo": None,
            "gender": "unknown",
            "birthDate": None,
            "deathDate": None,
            "birthPlace": None,
            "heightCm": None,
            "imdbId": None,
            "tmdbId": None,
            "wikipediaRo": None,
            "wikipediaEn": None,
            "romanian": False,
            "credits": [],
        },
    )
    if romanian:
        rec["romanian"] = True
    name = (row.get("personLabel") or "").strip()
    if name and not name.startswith("Q") and (not rec["name"] or len(name) > len(rec["name"])):
        rec["name"] = name
    desc = (row.get("personDescription") or "").strip()
    if desc and len(desc) > len(rec["description"]):
        rec["description"] = desc
    if row.get("image") and not rec["photo"]:
        rec["photo"] = commons_thumb(row["image"])
    if rec["gender"] == "unknown":
        rec["gender"] = gender_of(row.get("genderLabel"), row.get("gender"))
    if row.get("birthDate") and not rec["birthDate"]:
        rec["birthDate"] = row["birthDate"][:10]
    if row.get("deathDate") and not rec["deathDate"]:
        rec["deathDate"] = row["deathDate"][:10]
    if row.get("placeLabel") and not rec["birthPlace"]:
        rec["birthPlace"] = row["placeLabel"]
    if row.get("height") and not rec["heightCm"]:
        try:
            rec["heightCm"] = round(float(row["height"]))
        except ValueError:
            pass
    if row.get("imdb") and not rec["imdbId"]:
        rec["imdbId"] = row["imdb"]
    if row.get("tmdb") and not rec["tmdbId"]:
        rec["tmdbId"] = row["tmdb"]
    if row.get("articleRo"):
        rec["wikipediaRo"] = row["articleRo"]
    if row.get("articleEn"):
        rec["wikipediaEn"] = row["articleEn"]


def add_credit(store: dict[str, dict], row: dict) -> None:
    pid = qid(row.get("person"))
    if not pid:
        return
    rec = store.setdefault(
        pid,
        {
            "id": pid,
            "name": "",
            "description": "",
            "photo": None,
            "gender": "unknown",
            "birthDate": None,
            "deathDate": None,
            "birthPlace": None,
            "heightCm": None,
            "imdbId": None,
            "tmdbId": None,
            "wikipediaRo": None,
            "wikipediaEn": None,
            "romanian": False,
            "credits": [],
        },
    )
    title = (row.get("workLabel") or "").strip()
    year = year_of(row.get("date"))
    kind = qid(row.get("kind"))
    medium = MEDIUM.get(kind or "", "film")
    if not title or not year or year < 2016:
        return
    cred = {"title": title, "year": year, "medium": medium}
    if cred not in rec["credits"]:
        rec["credits"].append(cred)


def is_relevant(rec: dict) -> bool:
    name = rec.get("name") or ""
    if not name or name.startswith("Q"):
        return False
    if rec.get("deathDate"):
        return False
    birth = year_of(rec.get("birthDate"))
    if birth and birth < 1920:
        return False
    if birth and birth > 2012:
        return False
    if not rec.get("romanian"):
        return False
    # Keep living/recent Romanian screen talent even when Wikidata filmography is thin.
    has_signal = bool(
        rec.get("photo")
        or rec.get("imdbId")
        or rec.get("wikipediaRo")
        or rec.get("wikipediaEn")
        or rec.get("credits")
        or rec.get("description")
    )
    return has_signal


def main() -> None:
    store: dict[str, dict] = {}

    for row in fetch_wikidata_people():
        merge_person(store, row, romanian=True)
    for row in fetch_born_in_romania_actors():
        merge_person(store, row, romanian=True)

    credit_rows = fetch_credits()
    for row in credit_rows:
        add_credit(store, row)

    print("Wikipedia: photos and bios via article links…")
    need_ro: list[str] = []
    need_en: list[str] = []
    title_to_ids: dict[str, list[str]] = {}
    for rec in store.values():
        if not rec.get("romanian"):
            continue
        if rec.get("photo") and rec.get("description"):
            continue
        url = rec.get("wikipediaRo") or rec.get("wikipediaEn")
        if not url:
            continue
        title = urllib.parse.unquote(url.rsplit("/", 1)[-1]).replace("_", " ")
        title_to_ids.setdefault(title, []).append(rec["id"])
        if rec.get("wikipediaRo"):
            need_ro.append(title)
        else:
            need_en.append(title)
    for api, titles, cache_key in (
        (RO_API, sorted(set(need_ro)), "ro_sitelink_meta"),
        (EN_API, sorted(set(need_en)), "en_sitelink_meta"),
    ):
        if not titles:
            continue
        cached_meta = load_cache(cache_key)
        if cached_meta is None:
            try:
                cached_meta = wikipedia_pages_meta(api, titles)
                save_cache(cache_key, cached_meta)
            except Exception as exc:  # noqa: BLE001
                print(f"  {cache_key} failed ({exc})")
                cached_meta = {}
        print(f"  {cache_key}: {len(cached_meta)} pages")
        for meta in cached_meta.values():
            for pid in title_to_ids.get(meta.get("title") or "", []):
                rec = store[pid]
                if meta.get("extract") and len(meta["extract"]) > len(rec.get("description") or ""):
                    rec["description"] = meta["extract"]
                if meta.get("thumb") and not rec.get("photo"):
                    rec["photo"] = meta["thumb"]

    # Fill remaining stubs via a targeted entity lookup
    missing = [
        pid
        for pid, rec in store.items()
        if rec.get("romanian") and (not rec.get("name") or rec["name"].startswith("Q"))
    ]
    if missing:
        print(f"Wikidata: filling {len(missing)} stub names…")
        for i in range(0, len(missing), 60):
            chunk = " ".join(f"wd:{x}" for x in missing[i : i + 60])
            query = f"""
            SELECT ?person ?personLabel ?personDescription ?image ?gender ?genderLabel
                   ?birthDate ?deathDate ?imdb ?tmdb ?placeLabel ?articleRo ?articleEn
            WHERE {{
              VALUES ?person {{ {chunk} }}
              OPTIONAL {{ ?person wdt:P18 ?image }}
              OPTIONAL {{ ?person wdt:P21 ?gender }}
              OPTIONAL {{ ?person wdt:P569 ?birthDate }}
              OPTIONAL {{ ?person wdt:P570 ?deathDate }}
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
            try:
                for row in sparql(query):
                    merge_person(store, row)
            except Exception as exc:  # noqa: BLE001
                print(f"  stub chunk failed: {exc}")
            time.sleep(0.5)

    known_ids = [
        pid
        for pid, rec in store.items()
        if rec.get("romanian") and rec.get("name") and not rec["name"].startswith("Q")
    ]
    extra_credits = fetch_person_credits(known_ids)
    for row in extra_credits:
        add_credit(store, row)

    actors = []
    for rec in store.values():
        if not is_relevant(rec):
            continue
        rec["credits"] = sorted(rec["credits"], key=lambda c: (-c["year"], c["title"]))
        rec["recentCreditCount"] = len(rec["credits"])
        rec["latestYear"] = rec["credits"][0]["year"] if rec["credits"] else None
        media = {c["medium"] for c in rec["credits"]}
        rec["media"] = sorted(media)
        actors.append(rec)

    actors.sort(key=lambda a: (-(a["recentCreditCount"]), -(a["latestYear"] or 0), a["name"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generatedAt": time.strftime("%Y-%m-%d"),
        "sources": [
            "Wikidata (CC0)",
            "Wikipedia / Wikimedia Commons (CC BY-SA)",
        ],
        "note": (
            "Romanian screen actors compiled from public data. Credits cover film, "
            "television and shorts from 2016 onward where Wikidata has cast lists. "
            "Living actors without a structured recent credit are still included when "
            "Wikipedia/Wikidata identifies them as Romanian film or television actors, "
            "because public databases are incomplete — always verify availability."
        ),
        "count": len(actors),
        "withPhoto": sum(1 for a in actors if a.get("photo")),
        "withRecentCredits": sum(1 for a in actors if a.get("credits")),
        "actors": actors,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(actors)} actors ({payload['withPhoto']} photos) → {OUT}")


if __name__ == "__main__":
    main()
