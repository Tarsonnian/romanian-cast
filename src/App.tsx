import { useMemo, useState } from "react";
import db from "./data/actors.json";
import ActorCard from "./components/ActorCard";
import Profile from "./components/Profile";
import { ageFrom, matchesQuery } from "./lib/format";
import { photoSrc } from "./lib/photo";
import { exportShortlistText, loadShortlist, saveShortlist } from "./lib/shortlist";
import type { Actor, Database, Filters, Medium } from "./types";

const data = db as Database;
const actors: Actor[] = data.actors;

type SortKey = "credits" | "name" | "age";

const emptyFilters: Filters = {
  query: "",
  gender: "all",
  ageMin: 16,
  ageMax: 100,
  medium: "all",
  photoOnly: false,
  recentOnly: false,
  shortlistedOnly: false,
};

export default function App() {
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [sort, setSort] = useState<SortKey>("credits");
  const [openId, setOpenId] = useState<string | null>(null);
  const [shortlist, setShortlist] = useState<string[]>(() => loadShortlist());

  function toggleShortlist(id: string) {
    setShortlist((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      saveShortlist(next);
      return next;
    });
  }

  const visible = useMemo(() => {
    const list = actors.filter((actor) => {
      if (!matchesQuery(actor, filters.query)) return false;
      if (filters.gender !== "all" && actor.gender !== filters.gender) return false;
      if (filters.medium !== "all" && !actor.media.includes(filters.medium)) return false;
      if (filters.photoOnly && !actor.photo) return false;
      if (filters.recentOnly && actor.credits.length === 0) return false;
      if (filters.shortlistedOnly && !shortlist.includes(actor.id)) return false;
      const age = ageFrom(actor.birthDate, actor.deathDate);
      if (age != null && (age < filters.ageMin || age > filters.ageMax)) return false;
      if (age == null && (filters.ageMin > 16 || filters.ageMax < 100)) return false;
      return true;
    });

    list.sort((a, b) => {
      if (sort === "name") return a.name.localeCompare(b.name, "ro");
      if (sort === "age") {
        return (ageFrom(a.birthDate) ?? 999) - (ageFrom(b.birthDate) ?? 999);
      }
      if (b.recentCreditCount !== a.recentCreditCount) {
        return b.recentCreditCount - a.recentCreditCount;
      }
      return a.name.localeCompare(b.name, "ro");
    });
    return list;
  }, [filters, sort, shortlist]);

  const open = actors.find((a) => a.id === openId) ?? null;
  const shortlistedActors = shortlist
    .map((id) => actors.find((a) => a.id === id))
    .filter((a): a is Actor => Boolean(a));

  function copyShortlist() {
    const text = exportShortlistText(shortlistedActors.map((a) => a.name));
    void navigator.clipboard.writeText(text);
  }

  return (
    <div className="app">
      <header className="topbar">
        <div className="topbar-row">
          <div className="brand">
            <img
              className="brand-logo"
              src="/brand/logo-on-dark.png"
              alt="Substratum"
              width={120}
              height={100}
            />
            <div className="brand-copy">
              <h1 className="brand-name">CAST APP</h1>
              <p className="brand-sub">Romanian screen actors · 2016–2026</p>
            </div>
          </div>
          <div className="stats">
            <div>
              <strong>{data.count.toLocaleString("en")}</strong>
              in database
            </div>
            <div>
              <strong>{data.withPhoto.toLocaleString("en")}</strong>
              with photos
            </div>
            <div>
              <strong>{shortlist.length}</strong>
              shortlisted
            </div>
          </div>
        </div>
        <div className="toolbar">
          <label className="search">
            <span>Search</span>
            <input
              value={filters.query}
              onChange={(e) => setFilters((f) => ({ ...f, query: e.target.value }))}
              placeholder="Name, film, city…"
            />
          </label>
          <label className="field">
            <span>Gender</span>
            <select
              value={filters.gender}
              onChange={(e) =>
                setFilters((f) => ({ ...f, gender: e.target.value as Filters["gender"] }))
              }
            >
              <option value="all">All</option>
              <option value="female">Female</option>
              <option value="male">Male</option>
              <option value="unknown">Unspecified</option>
            </select>
          </label>
          <label className="field">
            <span>Age from</span>
            <select
              value={filters.ageMin}
              onChange={(e) => setFilters((f) => ({ ...f, ageMin: Number(e.target.value) }))}
            >
              {[16, 18, 20, 25, 30, 35, 40, 45, 50, 60, 70].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Age to</span>
            <select
              value={filters.ageMax}
              onChange={(e) => setFilters((f) => ({ ...f, ageMax: Number(e.target.value) }))}
            >
              {[25, 30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <div className="toggles">
            <span>Show</span>
            <div className="toggle-row">
              <button
                type="button"
                className={`chip ${filters.medium === "film" ? "on" : ""}`}
                onClick={() =>
                  setFilters((f) => ({ ...f, medium: f.medium === "film" ? "all" : "film" }))
                }
              >
                Film
              </button>
              <button
                type="button"
                className={`chip ${filters.medium === "tv" ? "on" : ""}`}
                onClick={() =>
                  setFilters((f) => ({ ...f, medium: f.medium === "tv" ? "all" : "tv" }))
                }
              >
                TV
              </button>
              <button
                type="button"
                className={`chip ${filters.medium === "short" ? "on" : ""}`}
                onClick={() =>
                  setFilters((f) => ({
                    ...f,
                    medium: f.medium === "short" ? "all" : ("short" as Medium),
                  }))
                }
              >
                Shorts
              </button>
              <button
                type="button"
                className={`chip ${filters.photoOnly ? "on" : ""}`}
                onClick={() => setFilters((f) => ({ ...f, photoOnly: !f.photoOnly }))}
              >
                Photos
              </button>
              <button
                type="button"
                className={`chip ${filters.recentOnly ? "on" : ""}`}
                onClick={() => setFilters((f) => ({ ...f, recentOnly: !f.recentOnly }))}
              >
                Known 2016+
              </button>
              <button
                type="button"
                className={`chip ${filters.shortlistedOnly ? "on" : ""}`}
                onClick={() =>
                  setFilters((f) => ({ ...f, shortlistedOnly: !f.shortlistedOnly }))
                }
              >
                Shortlist
              </button>
            </div>
          </div>
        </div>
        <p className="note">
          Public data snapshot {data.generatedAt}. Photos: Wikimedia. Always confirm rights and
          availability with the actor or their agent.
        </p>
      </header>

      <main className="main">
        <div className="meta-row">
          <div>
            {visible.length.toLocaleString("en")} actors
          </div>
          <button
            className="sort"
            type="button"
            onClick={() =>
              setSort((s) => (s === "credits" ? "name" : s === "name" ? "age" : "credits"))
            }
          >
            Sort: {sort === "credits" ? "recent credits" : sort === "name" ? "name" : "age"}
          </button>
        </div>

        {visible.length === 0 ? (
          <div className="empty">
            <h2>No one matches</h2>
            <p>Widen the age range or clear a filter — the shortlist stays as you left it.</p>
          </div>
        ) : (
          <div className="grid">
            {visible.map((actor) => (
              <ActorCard
                key={actor.id}
                actor={actor}
                shortlisted={shortlist.includes(actor.id)}
                onOpen={() => setOpenId(actor.id)}
                onToggleShortlist={() => toggleShortlist(actor.id)}
              />
            ))}
          </div>
        )}
        <p className="note">
          Internal catalog. Portrait photos from TMDB where available. This product uses the TMDB API
          but is not endorsed or certified by TMDB.
        </p>
      </main>

      {open && (
        <Profile
          actor={open}
          shortlisted={shortlist.includes(open.id)}
          onClose={() => setOpenId(null)}
          onToggleShortlist={() => toggleShortlist(open.id)}
        />
      )}

      {shortlistedActors.length > 0 && (
        <div className="shortlist">
          <div className="shortlist-inner">
            <h3>Shortlist · {shortlistedActors.length}</h3>
            <div className="shortlist-people">
              {shortlistedActors.map((actor) => (
                <button
                  key={actor.id}
                  className="mini"
                  type="button"
                  title={actor.name}
                  onClick={() => setOpenId(actor.id)}
                >
                  {photoSrc(actor.photo) ? (
                    <img src={photoSrc(actor.photo)!} alt={actor.name} />
                  ) : (
                    <span>{actor.name[0]}</span>
                  )}
                </button>
              ))}
            </div>
            <button className="btn" type="button" onClick={copyShortlist}>
              Copy names
            </button>
            <button className="btn" type="button" onClick={() => { saveShortlist([]); setShortlist([]); }}>
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
