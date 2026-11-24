const KEY = "romanian-cast-shortlist";

export function loadShortlist(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((x) => typeof x === "string") : [];
  } catch {
    return [];
  }
}

export function saveShortlist(ids: string[]): void {
  localStorage.setItem(KEY, JSON.stringify(ids));
}

export function exportShortlistText(names: string[]): string {
  return names.map((n, i) => `${i + 1}. ${n}`).join("\n");
}
