import type { Actor, Credit, Medium } from "../types";

export function ageFrom(birthDate: string | null, deathDate: string | null = null): number | null {
  if (!birthDate) return null;
  const born = new Date(birthDate);
  const end = deathDate ? new Date(deathDate) : new Date();
  if (Number.isNaN(born.getTime())) return null;
  let age = end.getFullYear() - born.getFullYear();
  const m = end.getMonth() - born.getMonth();
  if (m < 0 || (m === 0 && end.getDate() < born.getDate())) age -= 1;
  return age;
}

export function initials(name: string): string {
  const parts = name
    .replace(/[()]/g, " ")
    .split(/\s+/)
    .filter((p) => p && !p.startsWith("("));
  const first = parts[0]?.[0] ?? "";
  const last = parts.length > 1 ? parts[parts.length - 1][0] : "";
  return (first + last).toUpperCase();
}

export function mediumLabel(medium: Medium): string {
  if (medium === "film") return "Film";
  if (medium === "tv") return "TV";
  return "Short";
}

export function creditLine(credits: Credit[], limit = 3): string {
  if (!credits.length) return "Credits not listed in public data";
  return credits
    .slice(0, limit)
    .map((c) => `${c.title} (${c.year})`)
    .join(" · ");
}

export function genderLabel(gender: Actor["gender"]): string {
  if (gender === "female") return "Female";
  if (gender === "male") return "Male";
  if (gender === "nonbinary") return "Non-binary";
  return "Unspecified";
}

export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/ș/g, "s")
    .replace(/ț/g, "t");
}

export function matchesQuery(actor: Actor, query: string): boolean {
  const q = normalize(query.trim());
  if (!q) return true;
  const hay = normalize(
    [
      actor.name,
      actor.description,
      actor.birthPlace ?? "",
      ...actor.credits.map((c) => c.title),
    ].join(" "),
  );
  return q.split(/\s+/).every((part) => hay.includes(part));
}
