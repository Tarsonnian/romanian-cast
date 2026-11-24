import type { Actor } from "../types";
import { ageFrom, genderLabel, initials, mediumLabel } from "../lib/format";
import { photoSrc } from "../lib/photo";

interface Props {
  actor: Actor;
  shortlisted: boolean;
  onClose: () => void;
  onToggleShortlist: () => void;
}

export default function Profile({ actor, shortlisted, onClose, onToggleShortlist }: Props) {
  const age = ageFrom(actor.birthDate, actor.deathDate);

  return (
    <>
      <div className="drawer-backdrop" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label={actor.name}>
        <div className="drawer-photo">
          {photoSrc(actor.photo) ? (
            <img src={photoSrc(actor.photo)!} alt="" />
          ) : (
            <div className="poster-fallback">{initials(actor.name)}</div>
          )}
          <button className="drawer-close" type="button" onClick={onClose}>
            Close
          </button>
        </div>
        <div className="drawer-body">
          <p className="drawer-kicker">Romanian screen · 2016–2026</p>
          <h2>{actor.name}</h2>
          <div className="drawer-actions">
            <button className="btn primary" type="button" onClick={onToggleShortlist}>
              {shortlisted ? "Remove from shortlist" : "Add to shortlist"}
            </button>
            {actor.imdbId && (
              <a
                className="btn"
                href={`https://www.imdb.com/name/${actor.imdbId}/`}
                target="_blank"
                rel="noreferrer"
              >
                IMDb
              </a>
            )}
            {actor.wikipediaRo && (
              <a className="btn" href={actor.wikipediaRo} target="_blank" rel="noreferrer">
                Wikipedia
              </a>
            )}
            {actor.tmdbId && (
              <a
                className="btn"
                href={`https://www.themoviedb.org/person/${actor.tmdbId}`}
                target="_blank"
                rel="noreferrer"
              >
                TMDB
              </a>
            )}
          </div>
          <dl className="facts">
            <div>
              <dt>Age</dt>
              <dd>{age ?? "—"}{actor.deathDate ? " (deceased)" : ""}</dd>
            </div>
            <div>
              <dt>Gender</dt>
              <dd>{genderLabel(actor.gender)}</dd>
            </div>
            <div>
              <dt>Born</dt>
              <dd>
                {[actor.birthDate?.slice(0, 4), actor.birthPlace].filter(Boolean).join(" · ") || "—"}
              </dd>
            </div>
            <div>
              <dt>Height</dt>
              <dd>{actor.heightCm ? `${actor.heightCm} cm` : "—"}</dd>
            </div>
          </dl>
          {actor.description && <p className="bio">{actor.description}</p>}
          <section className="credits">
            <h3>Known credits since 2016</h3>
            {actor.credits.length ? (
              <ul>
                {actor.credits.map((c) => (
                  <li key={`${c.title}-${c.year}-${c.medium}`}>
                    <span>
                      {c.title}
                      <span className="kind">{mediumLabel(c.medium)}</span>
                    </span>
                    <span className="year">{c.year}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="bio">
                No structured film/TV credits since 2016 in Wikidata. They may still be working —
                check IMDb or their agent.
              </p>
            )}
          </section>
        </div>
      </aside>
    </>
  );
}
