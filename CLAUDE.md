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
- **streamlit** — the UI (`apps/streamlit-dashboard/app/main.py`).

Python 3.13. Install with `pip install -r apps/streamlit-dashboard/requirements.txt`.

## Architecture

Monorepo: `apps/` (samodzielne aplikacje) + `packages/` (kod współdzielony Pythona).

    apps/streamlit-dashboard/   Streamlit MVP (Python) — domyślny kontekst tego pliku.
      app/                      Streamlit UI — presentation only (entrypoint: app/main.py).
      src/processing/           Domain logic: identity resolution, cross-league
                                normalization, statistics (app-specific).
      src/cache/                ProfileStore — kuratorskie profile (profiles.db).
      src/paths.py              Centralne ścieżki baz per domena.
      draft_analyzer/           Zakładki draftów/graczy/kohorty + warstwa danych (db.py).
      data/                     Bazy per domena: profiles/cache/drafts/players/cohort.db.
    apps/web/                   Next.js 16 + Drizzle + Postgres (produkcja). W pełni izolowany.
    apps/gem-finder/            Pipeline CLI (Leaguepedia→lolpros→Riot→SQLite) + hidden_gems.
    packages/shared/shared/     Wspólny kod Pythona (importowany jako `shared.*`):
      api/                      Data-source clients (Riot, Leaguepedia). Raw FETCH only.
      lolpros.py                Scraper kont z lolpros.gg.
      processing/match_stats.py Czysta redukcja Match-V5 → metryki.

Aplikacje Pythona dokładają `packages/shared` do `sys.path` małym bootstrapem
(`app/main.py`, `gem-finder/scouting/__init__.py`, testy).

### Layer rules — keep these strict

- **`shared/api/` does not normalize.** A client returns data in a shape close
  to the source. It must not rename fields to a canonical schema, map roles,
  or compute derived values. Renaming, role mapping, and Z-scores belong in
  `src/processing/` (per aplikacji). This keeps sources swappable and
  normalization in one place.
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
(`get` / `set` with TTL). The default implementation is `SqliteCacheStore`
(`packages/shared/shared/api/riot_client.py`). Po podziale na bazy per domena
cache i profile mają OSOBNE pliki — `data/cache.db` (api_cache) vs
`data/profiles.db` (profiles); ścieżki w `apps/streamlit-dashboard/src/paths.py`.
Clients depend on the Protocol, not the concrete class, so the backend is
swappable. Zapytania kohorty łączą `cohort.db` z `players.db` przez
`ATTACH DATABASE` (zob. `draft_analyzer/db.py`: `get_conn_cohort`).

## Run

    cd apps/streamlit-dashboard
    pip install -r requirements.txt
    streamlit run app/main.py

Requires a `.env` in `apps/streamlit-dashboard/` with `RIOT_API_KEY=RGAPI-...`
(ścieżka liczona względem `src/config.py`, niezależna od cwd). Bazy SQLite
powstają w `apps/streamlit-dashboard/data/` (override: `DASHBOARD_DATA_DIR`).
Jednorazowa migracja ze starego układu: `python scripts/migrate_dbs.py`.

Optionally add a Leaguepedia bot-password (created at
`Special:BotPasswords` on lol.fandom.com) to raise the Cargo API rate
limit used by the Draft Analyzer / Database tabs:

    LEAGUEPEDIA_USERNAME=YourName@BotName
    LEAGUEPEDIA_PASSWORD=generated-bot-password

Without it the app still runs, just with the lower anonymous limit.

`app/main.py` `get_resolver()` wires the live `ProfileResolver`
(`RiotClient` + `LeaguepediaClient`), which share `data/cache.db` for the
API response cache. A Riot dev key expires every 24h — refresh it when
calls start returning 401/403. `StubResolver`
(`src/processing/stub_resolver.py`) stays available for offline use.
