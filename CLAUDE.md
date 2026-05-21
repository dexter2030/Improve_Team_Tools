# CLAUDE.md

Guidance for working in this repository.

## Project

**LoL Scouting Dashboard** — a Streamlit app for League of Legends talent
scouts. A coach tracks prospects; the app resolves their identities against
live data sources (Riot API for SoloQ, Leaguepedia for pro play) and
surfaces cross-league comparisons.

## Stack

- **riotwatcher** — Riot API client (Account-V1, Summoner-V4, ...).
- **mwclient** — MediaWiki client for the Leaguepedia Cargo API.
- **pandas** / **numpy** — data wrangling and cross-cohort statistics.
- **streamlit** — the UI (`app/main.py`).

Python 3.13. Install with `pip install -r requirements.txt`.

## Architecture

    app/             Streamlit UI — presentation only.
    src/api/         Data-source clients. Raw FETCH only — no normalization.
    src/processing/  Domain logic: identity resolution, cross-league
                     normalization, statistics.
    src/cache/       SQLite persistence (curated profiles + API response cache).

### Layer rules — keep these strict

- **`src/api/` does not normalize.** A client returns data in a shape close
  to the source. It must not rename fields to a canonical schema, map roles,
  or compute derived values. Renaming, role mapping, and Z-scores belong in
  `src/processing/`. This keeps sources swappable and normalization in one
  place.
- **Cross-league logic lives in `src/processing/`.** Comparing a player from
  one league against another — normalization, cohort Z-scores, role
  mapping — happens here, never in `api/` or `app/`.

## Key domain concepts

### Scouting profile = identity keys + metadata, never frozen stats

A `ScoutingProfile` (`src/processing/profiles.py`) holds only:

1. **Identity keys** — the minimum needed to FETCH stats (Riot ID, pro name).
2. **Scouting metadata** — hand-authored coach knowledge (age, tags, notes).

It never holds stats. Stats are volatile and cohort-relative; they are
fetched fresh and cached, never frozen into a profile. Freezing them would
rot the coach's notes against stale numbers and break recomputing Z-scores
against a new cohort. Do not add stat fields to profiles.

### Pro-play join key = Leaguepedia Link

A pro player is joined across Leaguepedia tables by their **`Link`** — the
canonical wiki page name — not their current in-game name. In-game names
change; `Link` is stable. The resolver maps a coach-supplied display name to
a `Link`, disambiguating by role and surfacing ambiguity to the coach rather
than guessing.

### Cache = SQLite behind the `CacheStore` Protocol

API responses are cached through the `CacheStore` structural Protocol
(`get` / `set` with TTL). The default implementation is `SqliteCacheStore`,
which shares the single `scouting.db` file with `ProfileStore` (separate
tables). Clients depend on the Protocol, not the concrete class, so the
backend is swappable.

## Run

    pip install -r requirements.txt
    streamlit run app/main.py

Requires a `.env` at the project root with `RIOT_API_KEY=RGAPI-...`.

Optionally add a Leaguepedia bot-password (created at
`Special:BotPasswords` on lol.fandom.com) to raise the Cargo API rate
limit used by the Draft Analyzer / Database tabs:

    LEAGUEPEDIA_USERNAME=YourName@BotName
    LEAGUEPEDIA_PASSWORD=generated-bot-password

Without it the app still runs, just with the lower anonymous limit.

`app/main.py` `get_resolver()` wires the live `ProfileResolver`
(`RiotClient` + `LeaguepediaClient`), which share `scouting.db` for the
API response cache. A Riot dev key expires every 24h — refresh it when
calls start returning 401/403. `StubResolver`
(`src/processing/stub_resolver.py`) stays available for offline use.
