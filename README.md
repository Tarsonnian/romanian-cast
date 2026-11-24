# CAST — Romanian screen actors

Local casting board of Romanian actors who work in film, television, and shorts (2016–2026). Built for internal production use: search, filter, open a profile, shortlist.

## Run it

```bash
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

The shortlist is stored in this browser only. Copy names when you want to send them to a producer or CD.

## What’s in the database

Public data from **Wikidata** (CC0) and **Wikipedia / Wikimedia Commons** (CC BY-SA). Headshots come from **TMDB** where available. This product uses the TMDB API but is not endorsed or certified by TMDB.

Credits are only as complete as Wikidata’s cast lists. Someone missing a 2016+ credit in this app may still be working — check IMDb from their profile.

Refresh the snapshot:

```bash
npm run data
```

## Not a rights database

Confirm availability, union status, and image rights with the actor or their agent before attaching anyone to a project.
