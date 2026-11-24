export type Gender = "female" | "male" | "nonbinary" | "unknown";
export type Medium = "film" | "tv" | "short";

export interface Credit {
  title: string;
  year: number;
  medium: Medium;
}

export interface Actor {
  id: string;
  name: string;
  description: string;
  photo: string | null;
  gender: Gender;
  birthDate: string | null;
  deathDate: string | null;
  birthPlace: string | null;
  heightCm: number | null;
  imdbId: string | null;
  tmdbId: string | null;
  wikipediaRo: string | null;
  wikipediaEn: string | null;
  romanian: boolean;
  credits: Credit[];
  recentCreditCount: number;
  latestYear: number | null;
  media: Medium[];
}

export interface Database {
  generatedAt: string;
  sources: string[];
  note: string;
  count: number;
  withPhoto: number;
  withRecentCredits: number;
  actors: Actor[];
}

export interface Filters {
  query: string;
  gender: Gender | "all";
  ageMin: number;
  ageMax: number;
  medium: Medium | "all";
  photoOnly: boolean;
  recentOnly: boolean;
  shortlistedOnly: boolean;
}
