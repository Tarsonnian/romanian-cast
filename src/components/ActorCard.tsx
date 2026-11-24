import type { Actor } from "../types";
import { ageFrom, creditLine, initials } from "../lib/format";
import { photoSrc } from "../lib/photo";

interface Props {
  actor: Actor;
  shortlisted: boolean;
  onOpen: () => void;
  onToggleShortlist: () => void;
}

export default function ActorCard({ actor, shortlisted, onOpen, onToggleShortlist }: Props) {
  const age = ageFrom(actor.birthDate, actor.deathDate);
  const meta = [
    age ? `${age} yrs` : null,
    actor.deathDate ? "deceased" : null,
    actor.media.length ? actor.media.join(" · ") : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <article className="card">
      <div className="poster-wrap">
        <button className="card-hit" onClick={onOpen} type="button">
          <div className="poster">
            {photoSrc(actor.photo) ? (
              <img src={photoSrc(actor.photo) as string} alt="" loading="lazy" />
            ) : (
              <div className="poster-fallback">{initials(actor.name)}</div>
            )}
            <div className="poster-scrim" />
          </div>
        </button>
        <button
          className={`star ${shortlisted ? "on" : ""}`}
          type="button"
          aria-label={shortlisted ? "Remove from shortlist" : "Add to shortlist"}
          onClick={onToggleShortlist}
        >
          {shortlisted ? "★" : "☆"}
        </button>
      </div>
      <button className="card-hit" onClick={onOpen} type="button">
        <h2 className="card-name">{actor.name}</h2>
        <p className="card-meta">{meta || "Age not listed"}</p>
        <p className="card-credits">{creditLine(actor.credits)}</p>
      </button>
    </article>
  );
}
