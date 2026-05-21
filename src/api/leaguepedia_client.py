"""
src/api/leaguepedia_client.py

Single Leaguepedia (lol.fandom.com) client for ALL modules in the project.

Scope is intentionally broad enough that no other module needs its own
Leaguepedia fetcher:
  * `search_players_by_id` / `get_players` / `get_player_scoreboard`
        — identity resolution & per-player scoreboard (app/main.py via
          src/processing/resolver.py).
  * `get_scoreboard_stats`
        — richer per-game stats (Gold, Damage, TeamKills, ...) used by
          hidden_gems for league-wide cohort distributions.
  * `get_tournament_players` / `get_players_meta`
        — rosters with metadata, used by Gem-finder-main to seed its DB.
  * `iter_pick_ban_batches` / `count_drafts`
        — pick&ban sequences with pagination, used by draft_analyzer.
  * `cargo` (low-level)
        — escape hatch for one-off custom queries.

As an `api/`-layer module this class only FETCHES rows. It does no role
mapping, no aggregation, no cohort normalization — those live in
`src/processing/`. Pro-play identity is joined on the canonical wiki page
name (`OverviewPage`, exposed as `link`), never on the in-game handle.

The MediaWiki Cargo API rate-limits anonymous queries hard per IP. The
client honors a transient `ratelimited` error with exponential backoff,
and, if `LEAGUEPEDIA_USERNAME` / `LEAGUEPEDIA_PASSWORD` are set in the
environment, logs in with a bot-password to raise the limit. Without those
credentials it falls back to the (lower) anonymous limit.

All Cargo reads go through an optional `CacheStore` so identical queries
don't keep hitting the network.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from collections.abc import Callable
from typing import Any, Iterator

import mwclient
from mwclient.errors import APIError
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .riot_client import CacheStore

LOG = logging.getLogger(__name__)

_LEAGUEPEDIA_HOST = "lol.fandom.com"
_DEFAULT_USER_AGENT = (
    "lol-scouting-dashboard/0.1 (Leaguepedia client; identity + scouting)"
)

# Cargo's own per-query maximum. Bigger limits are silently truncated by
# the server, so we paginate above this.
_CARGO_LIMIT = 500
_CARGO_RETRY_ATTEMPTS = 4

# Cache TTLs picked per data class:
#   players       — rosters shift at splits, day-stale is fine
#   scoreboard    — per-game rows are immutable once written; 6h captures
#                   patches/new games without hammering the server
#   tournaments   — roster snapshots tied to a tournament; day-stale fine
#   picks&bans    — pure historical data, day-stale fine
_PLAYERS_CACHE_TTL    = 24 * 3600
_SCOREBOARD_CACHE_TTL =  6 * 3600
_TOURNAMENT_CACHE_TTL = 24 * 3600
_PICKS_CACHE_TTL      = 24 * 3600


# --- Identity row ------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class PlayerIdentityRow:
    """One `Players`-table row, reduced to what the resolver consumes.

    `link` is OverviewPage — the canonical page name and the stable join
    key for everything pro-play. `player_id` is the player's *current*
    in-game handle, which can change and be reused; never join on it.
    """
    link: str
    player_id: str
    team: str
    role: str


# --- Scoreboard row (minimal, used by champion_stats) -----------------------

@dataclass(frozen=True, slots=True)
class ScoreboardRow:
    """One `ScoreboardPlayers` row — raw per-game stats, no aggregation.

    `win` is parsed from Leaguepedia's "Yes" / "No" string. All numeric
    fields are coerced from the API's string representation; missing or
    empty values become 0 (data gaps in older matches).
    """
    game_id: str
    champion: str
    kills: int
    deaths: int
    assists: int
    cs: int
    win: bool


# --- The client --------------------------------------------------------------

class LeaguepediaClient:
    """Reads the Leaguepedia Cargo API via the MediaWiki client.

    Args:
        cache: optional read-through cache (any `CacheStore`). Pass a
               shared `SqliteCacheStore` so repeated lookups skip the
               network.
        user_agent: HTTP UA string; default identifies this project.
        site: a pre-built `mwclient.Site`, chiefly for tests. When omitted
              a Site for lol.fandom.com is created — note that
              constructing it performs one network call.
        login: when True (default), and `LEAGUEPEDIA_USERNAME` /
               `LEAGUEPEDIA_PASSWORD` are in env, log in to raise the
               anonymous rate limit. Failure to log in is logged but not
               raised; we fall back to anonymous mode.
    """

    def __init__(
        self,
        cache: CacheStore | None = None,
        *,
        user_agent: str = _DEFAULT_USER_AGENT,
        site: mwclient.Site | None = None,
        login: bool = True,
    ) -> None:
        self._cache = cache
        self._site = site if site is not None else mwclient.Site(
            _LEAGUEPEDIA_HOST,
            path="/",  # Fandom serves api.php at the root, not /w/.
            clients_useragent=user_agent,
        )
        self._auth_state: str = "anon"
        if login and site is None:
            self._maybe_login()

    # -- Auth ---------------------------------------------------------------

    def _maybe_login(self) -> None:
        """Log in with bot-password if env credentials are present.

        Bot-passwords are created at Special:BotPasswords on lol.fandom.com.
        Username format: 'YourName@BotName'. Failure is non-fatal so the
        client still works anonymously — but the auth state is recorded
        so the UI can warn the user.
        """
        username = os.environ.get("LEAGUEPEDIA_USERNAME")
        password = os.environ.get("LEAGUEPEDIA_PASSWORD")
        if not (username and password):
            return
        try:
            self._site.login(username, password)
        except Exception as err:
            LOG.warning("Leaguepedia bot-password login failed: %s", err)
            self._auth_state = "error"
            return
        self._auth_state = "bot"

    def auth_status(self) -> tuple[str, str]:
        """Auth mode as (level, message); level: ok / info / warn."""
        if self._auth_state == "bot":
            return ("ok",
                    "Leaguepedia: zalogowano bot-passwordem — "
                    "podwyższony limit API.")
        if self._auth_state == "error":
            return ("warn",
                    "Leaguepedia: logowanie bot-passwordem nie powiodło "
                    "się — sprawdź LEAGUEPEDIA_USERNAME / "
                    "LEAGUEPEDIA_PASSWORD w .env.")
        has_creds = bool(os.environ.get("LEAGUEPEDIA_USERNAME")
                         and os.environ.get("LEAGUEPEDIA_PASSWORD"))
        if has_creds:
            return ("info",
                    "Leaguepedia: bot-password skonfigurowany — logowanie "
                    "nastąpi przy pierwszym pobraniu.")
        return ("warn",
                "Leaguepedia: tryb anonimowy — niski limit API. Dodaj "
                "LEAGUEPEDIA_USERNAME i LEAGUEPEDIA_PASSWORD do .env.")

    # -- Identity rows ------------------------------------------------------

    def search_players_by_id(self, in_game_name: str) -> list[PlayerIdentityRow]:
        """Return `Players` rows whose current ID equals `in_game_name`.

        May return zero rows (un-signed prospect, or handle no pro uses),
        one, or several — a handle can be reused across players over
        time, so the caller is expected to disambiguate.
        """
        name = in_game_name.strip()
        if not name:
            return []
        return self._query_players(f"Players.ID='{_escape(name)}'")

    def get_players(
        self,
        *,
        player_link: str | None = None,
        team: str | None = None,
    ) -> list[PlayerIdentityRow]:
        """Return `Players` rows filtered by canonical link and/or team.

        At least one filter must be supplied; fetching the whole table is
        never the intent and would be a needlessly large request.
        """
        clauses: list[str] = []
        if player_link is not None:
            clauses.append(f"Players.OverviewPage='{_escape(player_link)}'")
        if team is not None:
            clauses.append(f"Players.Team='{_escape(team)}'")
        if not clauses:
            raise ValueError(
                "get_players needs at least one of player_link or team."
            )
        return self._query_players(" AND ".join(clauses))

    def get_players_meta(
        self,
        player_links: list[str],
        *,
        batch_pause: float = 0.5,
    ) -> dict[str, dict]:
        """Players metadata (ID, Country, Role, Retired) by OverviewPage.

        Used by Gem-finder-main to enrich tournament rosters. Returns a
        dict keyed by OverviewPage so callers can join by `link`. Chunked
        to keep WHERE clauses below MediaWiki's parse limit.

        `batch_pause` — krótka pauza między chunkami (sekundy), żeby nie
        wywołać rate-limita MediaWiki przy długiej liście. Pauzujemy
        tylko gdy chunk faktycznie poszedł do sieci (cache hit pomijamy),
        bo cache nie obciąża API.
        """
        if not player_links:
            return {}
        out: dict[str, dict] = {}
        chunk = 30
        for i in range(0, len(player_links), chunk):
            window = player_links[i : i + chunk]
            cache_key = f"lp:players_meta:{','.join(window)}"
            hit_network = self._cache_get(cache_key) is None
            ors = " OR ".join(
                [f"Players.OverviewPage='{_escape(p)}'" for p in window]
            )
            rows = self._cargo_cached(
                key=cache_key,
                tables="Players",
                fields=(
                    "Players.OverviewPage=OverviewPage,"
                    "Players.ID=ID,"
                    "Players.Team=Team,"
                    "Players.Role=Role,"
                    "Players.Country=Country,"
                    "Players.Residency=Residency,"
                    "Players.NationalityPrimary=NationalityPrimary,"
                    "Players.IsRetired=IsRetired"
                ),
                where=ors,
                ttl=_PLAYERS_CACHE_TTL,
            )
            for row in rows:
                page = row.get("OverviewPage")
                if page:
                    out[page] = row
            # Pauza między chunkami, ale nie po ostatnim ani po cache hicie.
            if hit_network and batch_pause > 0 and i + chunk < len(player_links):
                time.sleep(batch_pause)
        return out

    # -- Scoreboard (champion pool) ----------------------------------------

    def get_player_scoreboard(self, player_link: str) -> list[ScoreboardRow]:
        """Return `ScoreboardPlayers` rows for one player (by OverviewPage).

        Each row represents one pro game. Returns an empty list for
        players with no pro-play record or an unresolved link. Up to
        `_CARGO_LIMIT` (500) rows are returned — for most scouting use
        cases this covers the full career and is the Cargo per-query max.
        """
        link = player_link.strip()
        if not link:
            return []
        rows = self._cargo_cached(
            key=f"lp:scoreboard:Link='{_escape(link)}'",
            tables="ScoreboardPlayers",
            fields=(
                "ScoreboardPlayers.GameId=GameId,"
                "ScoreboardPlayers.Champion=Champion,"
                "ScoreboardPlayers.Kills=Kills,"
                "ScoreboardPlayers.Deaths=Deaths,"
                "ScoreboardPlayers.Assists=Assists,"
                "ScoreboardPlayers.CS=CS,"
                "ScoreboardPlayers.PlayerWin=PlayerWin"
            ),
            where=f"ScoreboardPlayers.Link='{_escape(link)}'",
            ttl=_SCOREBOARD_CACHE_TTL,
        )
        return [
            ScoreboardRow(
                game_id=row.get("GameId", ""),
                champion=row.get("Champion", ""),
                kills=_to_int(row.get("Kills")),
                deaths=_to_int(row.get("Deaths")),
                assists=_to_int(row.get("Assists")),
                cs=_to_int(row.get("CS")),
                win=row.get("PlayerWin", "").strip().lower() == "yes",
            )
            for row in rows
            if row.get("Champion")   # skip data-gap rows with no champion
        ]

    def get_scoreboard_stats(
        self,
        *,
        player_link: str | None = None,
        league: str | None = None,
    ) -> list[dict[str, Any]]:
        """Richer per-game stats joined with `ScoreboardGames`.

        Includes gold, damage, team kills/gold and game length — fields
        the bare `get_player_scoreboard` doesn't expose. Used by
        hidden_gems for league-wide cohort distributions.

        Exactly one of `player_link` or `league` is the minimum filter —
        an unfiltered query would be huge and instantly rate-limited.

        Returns dicts with typed numeric fields (no strings).
        """
        if player_link is None and league is None:
            raise ValueError(
                "get_scoreboard_stats wymaga `player_link` lub `league` "
                "(bez filtra zapytanie zaciągnie zbyt wiele wierszy)."
            )
        where_parts: list[str] = []
        if player_link is not None:
            where_parts.append(f"SP.Link='{_escape(player_link)}'")
        if league is not None:
            where_parts.append(f"SG.Tournament LIKE '%{_escape(league)}%'")
        where = " AND ".join(where_parts)

        rows = self._cargo_paginated(
            key=f"lp:scoreboard_stats:{where}",
            tables="ScoreboardPlayers=SP,ScoreboardGames=SG",
            fields=(
                "SP.Link=link,"
                "SP.Champion=champion,"
                "SP.Role=role,"
                "SP.Side=side,"
                "SP.PlayerWin=win,"
                "SG.Gamelength_Number=gamelen,"
                "SP.Kills=kills,"
                "SP.Deaths=deaths,"
                "SP.Assists=assists,"
                "SP.CS=cs,"
                "SP.Gold=gold,"
                "SP.DamageToChampions=damage,"
                "SP.TeamKills=team_kills,"
                "SP.TeamGold=team_gold,"
                "SG.Tournament=tournament,"
                "SG.DateTime_UTC=datetime"
            ),
            where=where,
            join_on="SP.GameId=SG.GameId",
            order_by="SG.DateTime_UTC DESC",
            ttl=_SCOREBOARD_CACHE_TTL,
        )

        out: list[dict[str, Any]] = []
        for r in rows:
            out.append({
                "link":             r.get("link", ""),
                "champion":         r.get("champion", ""),
                "role":             r.get("role", ""),
                "side":             r.get("side", ""),
                "win":              str(r.get("win", "")).strip().lower()
                                    == "yes",
                "gamelength_min":   _to_float(r.get("gamelen")),
                "kills":            _to_int(r.get("kills")),
                "deaths":           _to_int(r.get("deaths")),
                "assists":          _to_int(r.get("assists")),
                "cs":               _to_int(r.get("cs")),
                "gold":             _to_int(r.get("gold")),
                "damage_champions": _to_int(r.get("damage")),
                "team_kills":       _to_int(r.get("team_kills")),
                "team_gold":        _to_int(r.get("team_gold")),
                "tournament":       r.get("tournament", ""),
                "datetime":         r.get("datetime", ""),
            })
        return out

    # -- Tournament rosters --------------------------------------------------

    def get_tournament_players(
        self,
        leagues: list[str],
        active_since_date: str | None = None,
    ) -> dict[str, dict]:
        """Latest TournamentPlayers row per player across the given leagues.

        Used by Gem-finder-main to seed its DB with active rosters.

        `leagues` filters `Tournaments.League` (exact match per league).
        `active_since_date` is an ISO date — only tournaments starting on
        or after it are considered. Pass None to include all.

        Returns a dict keyed by Player (OverviewPage), values include
        Player / Team / Role / League / DateStart. Only the *latest*
        tournament per player is kept.
        """
        if not leagues:
            return {}
        leagues_filter = " OR ".join(
            [f'Tournaments.League="{_escape(lg)}"' for lg in leagues]
        )
        where = f"({leagues_filter})"
        if active_since_date:
            where += f' AND Tournaments.DateStart >= "{_escape(active_since_date)}"'

        rows = self._cargo_paginated(
            key=f"lp:tournament_players:{where}",
            tables="TournamentPlayers=TP,Tournaments",
            fields=(
                "TP.Player=Player,"
                "TP.Team=Team,"
                "TP.Role=Role,"
                "Tournaments.League=League,"
                "Tournaments.DateStart=DateStart"
            ),
            where=where,
            join_on="TP.OverviewPage=Tournaments.OverviewPage",
            order_by="Tournaments.DateStart DESC",
            ttl=_TOURNAMENT_CACHE_TTL,
        )
        latest: dict[str, dict] = {}
        for row in rows:
            p = row.get("Player")
            if not p or p in latest:
                continue
            latest[p] = row
        return latest

    def get_league_players(
        self,
        league: str,
        *,
        exclude_more_specific: list[str] | None = None,
        batch_pause: float = 0.5,
    ) -> list[dict]:
        """All unique players who appeared on any roster in tournaments
        whose name matches `league` as a substring (with exclusions).

        Two-step fetch:
          1. TournamentPlayers JOIN Tournaments — gives latest (team, role,
             tournament, date) per player_link for the league.
          2. Players-table metadata enrichment by OverviewPage — adds
             current in-game ID, country, residency, retired flag.

        Returns a list of dicts (one per unique player_link), most recent
        tournament first. Uses the same name-substring + exclusions
        mechanism as `iter_pick_ban_batches`, so it consistently matches
        the draft_analyzer's league definitions (e.g. "LFL" excludes
        "LFL Division 2").
        """
        where = f"Tournaments.Name LIKE '%{_escape(league)}%'"
        for excl in (exclude_more_specific or []):
            where += f" AND Tournaments.Name NOT LIKE '%{_escape(excl)}%'"

        rows = self._cargo_paginated(
            key=f"lp:league_players:{where}",
            tables="TournamentPlayers=TP,Tournaments",
            fields=(
                "TP.Player=Player,"
                "TP.Team=Team,"
                "TP.Role=Role,"
                "Tournaments.Name=Tournament,"
                "Tournaments.DateStart=DateStart"
            ),
            where=where,
            join_on="TP.OverviewPage=Tournaments.OverviewPage",
            order_by="Tournaments.DateStart DESC",
            ttl=_TOURNAMENT_CACHE_TTL,
        )

        latest: dict[str, dict] = {}
        for row in rows:
            link = row.get("Player")
            if not link or link in latest:
                continue
            latest[link] = {
                "link": link,
                "player_id": "",
                "team": row.get("Team", ""),
                "role": row.get("Role", ""),
                "tournament": row.get("Tournament", ""),
                "date_start": row.get("DateStart", ""),
                "country": "",
                "residency": "",
                "nationality_primary": "",
                "is_retired": "",
            }

        meta = self.get_players_meta(
            list(latest.keys()), batch_pause=batch_pause
        )
        for link, base in latest.items():
            m = meta.get(link, {})
            base["player_id"] = m.get("ID", "") or ""
            base["country"] = m.get("Country", "") or ""
            base["residency"] = m.get("Residency", "") or ""
            base["nationality_primary"] = m.get("NationalityPrimary", "") or ""
            base["is_retired"] = m.get("IsRetired", "") or ""
            if not base["role"]:
                base["role"] = m.get("Role", "") or ""

        return list(latest.values())

    def get_all_players(
        self,
        *,
        country: str | None = None,
        role: str | None = None,
        only_active: bool = False,
        on_batch: Callable[[int], None] | None = None,
        max_rows: int | None = None,
    ) -> list[dict]:
        """All rows from Leaguepedia's `Players` table — no league filter.

        Used by the "Players Data" tab to populate a global player browser
        with client-side filtering (nationality, role). Pagination is via
        the standard cargo offset walker; the Players table currently has
        ~30k rows, so a cold fetch is on the order of one minute.

        Filters (Country / Role / Retired) can be applied at the query
        layer to shrink the response. They are optional — passing none
        downloads the whole table. The values must match Leaguepedia's
        casing for Cargo equality to match.

        `only_active` skips rows whose `IsRetired` is truthy (Leaguepedia
        stores '1' for retired). NULL/empty is treated as active.

        `on_batch(total_so_far)` is called after each 500-row page —
        feeds a Streamlit progress bar from outside.
        """
        clauses: list[str] = []
        if country is not None:
            clauses.append(f"Players.Country='{_escape(country)}'")
        if role is not None:
            clauses.append(f"Players.Role='{_escape(role)}'")
        if only_active:
            clauses.append("(Players.IsRetired IS NULL "
                           "OR Players.IsRetired='' "
                           "OR Players.IsRetired='0')")
        where = " AND ".join(clauses)

        # Streaming pagination: we want progress feedback per page, so we
        # don't go through `_cargo_paginated` (which buffers internally).
        out: list[dict] = []
        offset = 0
        while True:
            batch = self._cargo_raw(
                tables="Players",
                fields=(
                    "Players.OverviewPage=OverviewPage,"
                    "Players.ID=ID,"
                    "Players.Team=Team,"
                    "Players.Role=Role,"
                    "Players.Country=Country,"
                    "Players.Residency=Residency,"
                    "Players.NationalityPrimary=NationalityPrimary,"
                    "Players.IsRetired=IsRetired"
                ),
                where=where,
                order_by="Players.OverviewPage ASC",
                limit=_CARGO_LIMIT,
                offset=offset,
            )
            if not batch:
                break
            out.extend(batch)
            if on_batch is not None:
                on_batch(len(out))
            if max_rows is not None and len(out) >= max_rows:
                out = out[:max_rows]
                break
            if len(batch) < _CARGO_LIMIT:
                break
            offset += _CARGO_LIMIT
            time.sleep(0.3)
        return out

    # -- Picks & Bans (draft_analyzer) --------------------------------------

    def iter_pick_ban_batches(
        self,
        league: str,
        *,
        season_where: str = "",
        exclude_more_specific: list[str] | None = None,
        max_rows: int = 20000,
        batch_pause: float = 1.5,
    ) -> Iterator[list[dict]]:
        """Stream pick&ban rows for a league, page by page (<=500 / batch).

        Joins `PicksAndBansS7` to `ScoreboardGames` via `MatchScheduleGame`
        (Leaguepedia documented bridge — PnB.GameId != SG.GameId directly).

        `exclude_more_specific` is a list of longer-named tournaments that
        also match the league substring (e.g. exclude "LFL Division 2"
        when querying "LFL"). The draft_analyzer's `leagues.more_specific`
        feeds this — kept out of api/ since it is project policy.

        Yields raw row dicts; normalization to b1/r1/.../winner is the
        caller's job (draft_analyzer._normalize). Stopping early is safe
        — anything yielded so far is still valid.
        """
        pnb_fields = (
            "PicksAndBansS7.GameId, "
            "PicksAndBansS7.Team1Ban1, PicksAndBansS7.Team1Ban2, "
            "PicksAndBansS7.Team1Ban3, PicksAndBansS7.Team1Ban4, "
            "PicksAndBansS7.Team1Ban5, "
            "PicksAndBansS7.Team2Ban1, PicksAndBansS7.Team2Ban2, "
            "PicksAndBansS7.Team2Ban3, PicksAndBansS7.Team2Ban4, "
            "PicksAndBansS7.Team2Ban5, "
            "PicksAndBansS7.Team1Pick1, PicksAndBansS7.Team1Pick2, "
            "PicksAndBansS7.Team1Pick3, PicksAndBansS7.Team1Pick4, "
            "PicksAndBansS7.Team1Pick5, "
            "PicksAndBansS7.Team2Pick1, PicksAndBansS7.Team2Pick2, "
            "PicksAndBansS7.Team2Pick3, PicksAndBansS7.Team2Pick4, "
            "PicksAndBansS7.Team2Pick5, "
            "PicksAndBansS7.Team1, PicksAndBansS7.Team2, "
            "PicksAndBansS7.Winner"
        )
        sg_fields = (
            "ScoreboardGames.Patch, ScoreboardGames.DateTime_UTC, "
            "ScoreboardGames.Tournament"
        )
        where = _build_league_where(league, exclude_more_specific)
        if season_where:
            where += f" AND {season_where}"

        offset = 0
        while offset < max_rows:
            batch = self._cargo_raw(
                tables="PicksAndBansS7, MatchScheduleGame, ScoreboardGames",
                fields=f"{pnb_fields}, {sg_fields}",
                where=where,
                join_on=(
                    "PicksAndBansS7.GameId=MatchScheduleGame.GameId,"
                    "MatchScheduleGame.GameId=ScoreboardGames.GameId"
                ),
                limit=_CARGO_LIMIT,
                offset=offset,
            )
            if not batch:
                return
            yield batch
            if len(batch) < _CARGO_LIMIT:
                return
            offset += _CARGO_LIMIT
            time.sleep(batch_pause)

    def count_drafts(
        self,
        league: str,
        *,
        season_where: str = "",
        exclude_more_specific: list[str] | None = None,
    ) -> int:
        """Number of pick&ban draft rows on Leaguepedia for `league`.

        Counts DISTINCT GameId, restricted to rows with at least one pick
        (same predicate the draft_analyzer uses when persisting). Matches
        the same 3-table join as `iter_pick_ban_batches`.
        """
        where = _build_league_where(league, exclude_more_specific)
        if season_where:
            where += f" AND {season_where}"
        where += f" AND {_HAS_PICKS_SQL}"

        rows = self._cargo_raw(
            tables="PicksAndBansS7, MatchScheduleGame, ScoreboardGames",
            fields="COUNT(DISTINCT PicksAndBansS7.GameId)=N",
            where=where,
            join_on=(
                "PicksAndBansS7.GameId=MatchScheduleGame.GameId,"
                "MatchScheduleGame.GameId=ScoreboardGames.GameId"
            ),
            limit=1,
            offset=0,
        )
        if not rows:
            return 0
        try:
            return int(next(iter(rows[0].values())))
        except (StopIteration, ValueError, TypeError):
            return 0

    # -- Low-level escape hatch ----------------------------------------------

    def cargo(
        self,
        *,
        tables: str,
        fields: str,
        where: str = "",
        join_on: str = "",
        order_by: str = "",
        group_by: str = "",
        max_rows: int | None = None,
    ) -> list[dict]:
        """Run a generic Cargo query with pagination. NOT cached.

        For one-off custom queries where the typed helpers don't fit.
        Prefer the typed helpers for anything used repeatedly.
        """
        return self._cargo_paginated(
            key=None,
            tables=tables,
            fields=fields,
            where=where,
            join_on=join_on,
            order_by=order_by,
            group_by=group_by,
            max_rows=max_rows,
            ttl=None,
        )

    # -- Internals -----------------------------------------------------------

    def _query_players(self, where: str) -> list[PlayerIdentityRow]:
        rows = self._cargo_cached(
            key=f"lp:players:{where}",
            tables="Players",
            fields=(
                "Players.OverviewPage=OverviewPage,"
                "Players.ID=ID,"
                "Players.Team=Team,"
                "Players.Role=Role"
            ),
            where=where,
            ttl=_PLAYERS_CACHE_TTL,
        )
        return [
            PlayerIdentityRow(
                link=row.get("OverviewPage", ""),
                player_id=row.get("ID", ""),
                team=row.get("Team", ""),
                role=row.get("Role", ""),
            )
            for row in rows
        ]

    def _cargo_cached(
        self,
        *,
        key: str,
        tables: str,
        fields: str,
        where: str,
        ttl: int,
        join_on: str = "",
        order_by: str = "",
    ) -> list[dict]:
        """Single-page (<=500 rows) cached Cargo query."""
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        rows = self._cargo_raw(
            tables=tables, fields=fields, where=where,
            join_on=join_on, order_by=order_by,
            limit=_CARGO_LIMIT, offset=0,
        )
        self._cache_set(key, rows, ttl)
        return rows

    def _cargo_paginated(
        self,
        *,
        key: str | None,
        tables: str,
        fields: str,
        where: str = "",
        join_on: str = "",
        order_by: str = "",
        group_by: str = "",
        max_rows: int | None = None,
        ttl: int | None,
    ) -> list[dict]:
        """Paginated Cargo query — walks `offset` until the last page.

        Optionally cached when `key` is given. `max_rows` caps the total
        rows returned (None = unlimited).
        """
        if key is not None and ttl is not None:
            cached = self._cache_get(key)
            if cached is not None:
                return cached

        out: list[dict] = []
        offset = 0
        while True:
            batch = self._cargo_raw(
                tables=tables, fields=fields, where=where,
                join_on=join_on, order_by=order_by, group_by=group_by,
                limit=_CARGO_LIMIT, offset=offset,
            )
            out.extend(batch)
            if max_rows is not None and len(out) >= max_rows:
                out = out[:max_rows]
                break
            if len(batch) < _CARGO_LIMIT:
                break
            offset += _CARGO_LIMIT
            time.sleep(0.3)   # gentle pacing between pages

        if key is not None and ttl is not None:
            self._cache_set(key, out, ttl)
        return out

    @retry(
        retry=retry_if_exception(lambda e: _is_transient(e)),
        wait=wait_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(_CARGO_RETRY_ATTEMPTS),
        reraise=True,
    )
    def _cargo_raw(
        self,
        *,
        tables: str,
        fields: str,
        where: str = "",
        join_on: str = "",
        order_by: str = "",
        group_by: str = "",
        limit: int = _CARGO_LIMIT,
        offset: int = 0,
    ) -> list[dict]:
        """Single Cargo call, retrying transient ratelimited errors only."""
        params: dict[str, Any] = {
            "tables": tables,
            "fields": fields,
            "limit": limit,
            "offset": offset,
        }
        if where:
            params["where"] = where
        if join_on:
            params["join_on"] = join_on
        if order_by:
            params["order_by"] = order_by
        if group_by:
            params["group_by"] = group_by

        result = self._site.api("cargoquery", **params)
        return [item["title"] for item in result.get("cargoquery", [])]

    # -- Cache helpers -------------------------------------------------------

    def _cache_get(self, key: str) -> list[dict] | None:
        return self._cache.get(key) if self._cache is not None else None

    def _cache_set(self, key: str, value: list[dict], ttl_seconds: int) -> None:
        if self._cache is not None:
            self._cache.set(key, value, ttl_seconds)


# --- Helpers ----------------------------------------------------------------

# Predicate: a draft row has at least one pick (10 slots Team{1,2}Pick{1..5}).
# Kept module-level since both iter_pick_ban_batches and count_drafts use it.
_HAS_PICKS_SQL = "(" + " OR ".join(
    f"PicksAndBansS7.Team{_t}Pick{_i} != ''"
    for _t in (1, 2) for _i in range(1, 6)
) + ")"


def _build_league_where(
    league: str,
    exclude_more_specific: list[str] | None,
) -> str:
    """WHERE clause for a league substring with exclusions.

    "LFL" must not catch "LFL Division 2"; the draft_analyzer decides
    which longer names to exclude (via `leagues.more_specific`) and
    passes them in.
    """
    clause = f"ScoreboardGames.Tournament LIKE '%{_escape(league)}%'"
    for excl in (exclude_more_specific or []):
        clause += f" AND ScoreboardGames.Tournament NOT LIKE '%{_escape(excl)}%'"
    return clause


def _is_transient(exc: BaseException) -> bool:
    """True for transient MediaWiki API errors worth retrying.

    Covers:
      * 'ratelimited' — per-IP throughput cap (sustained bulk loads).
      * 'internal_api_error_*' — server-side flake (MWException etc.);
        the server returns a different transient code each time but
        every one starts with this prefix.

    Permanent errors (badtoken, missingparam, no-such-table, ...) are
    NOT retried — they would just keep failing.
    """
    if not isinstance(exc, APIError):
        return False
    code = exc.code or ""
    return code == "ratelimited" or code.startswith("internal_api_error_")


# Backwards-compat alias for any external caller still importing the old name.
_is_ratelimited = _is_transient


def _escape(value: str) -> str:
    """Escape a string for safe interpolation into a Cargo WHERE clause."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _to_int(value: object) -> int:
    """Coerce a Cargo numeric value (string or None) to int.

    Older pro-play records occasionally have empty strings for numeric
    fields. Treat those as 0 so aggregation is still meaningful.
    """
    if value is None or value == "":
        return 0
    try:
        return int(float(value))   # "23" and "23.0" both round-trip
    except (ValueError, TypeError):
        return 0


def _to_float(value: object) -> float | None:
    """Coerce a Cargo numeric value to float; None on missing/garbage."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None
