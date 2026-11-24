/** Local cached headshots in /public/photos — never remote TMDB URLs. */
export function photoSrc(photo: string | null): string | null {
  if (!photo) return null;
  if (/^https?:\/\//i.test(photo)) return photo;
  const base = import.meta.env.BASE_URL;
  return photo.startsWith("/") ? `${base}${photo.slice(1)}` : `${base}${photo}`;
}
