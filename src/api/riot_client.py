"""
src/api/riot_client.py

Riot API client for the SoloQ identity-resolution path.

Scope is deliberately narrow. As an `api/`-layer module it only FETCHES:
given a Riot ID it returns a `RiotAccount` (PUUID + summoner level). It does
no normalization, no role mapping, no statistics — those belong in
`src/processing/`. The resolver in `src/processing/resolver.py` composes
this client; its `RiotClientProto` is the contract this class satisfies.

Resolution crosses two Riot endpoints:
  * Account-V1  — Riot ID  -> PUUID        (continental routing)
  * Summoner-V4 — PUUID    -> summoner level (platform routing)

Responses are read through an optional `CacheStore` so repeated lookups stay
well under Riot's rate limits.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Protocol

from riotwatcher import ApiError, LolWatcher, RiotWatcher


# --- Platform routing --------------------------------------------------------
# Account-V1 is served from continental ("regional") routing values, whereas
# Summoner-V4 uses platform routing values. resolve_account needs both, so it
# maps the caller's platform (e.g. 'euw1') to its region ('europe') here.
# OCE has no continental route of its own on Account-V1 and routes to americas.

PLATFORM_TO_REGION: dict[str, str] = {
    # Americas
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "oc1": "americas",
    # Europe
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    # Asia
    "kr": "asia",
    "jp1": "asia",
}


# --- Cache contract ----------------------------------------------------------

class CacheStore(Protocol):
    """Structural cache contract for the api/ layer.

    RiotClient — and the planned LeaguepediaClient — read through a cache
    that satisfies this Protocol, depending on the behavior rather than a
    concrete class so the backend (SQLite, in-memory, ...) stays swappable.

    This Protocol is declared here because RiotClient is the first api/
    client built; `leaguepedia_client.py` should import `CacheStore` from
    this module rather than redeclaring it.
    """

    def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or None if absent or expired."""
        ...

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        """Cache a JSON-serializable `value` under `key`, expiring it after
        `ttl_seconds` (None = no expiry)."""
        ...


_CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key      TEXT PRIMARY KEY,
    value          TEXT NOT NULL,   -- JSON-encoded payload
    expires_epoch  REAL             -- NULL = never expires
);
"""


class SqliteCacheStore:
    """SQLite-backed `CacheStore` for raw API responses.

    Lives in its own `api_cache` table so it can share the single
    `scouting.db` file with `ProfileStore` — one file to deploy. Expired
    rows are evicted lazily on read.
    """

    def __init__(self, db_path: str | Path = "scouting.db") -> None:
        self._db_path = str(db_path)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_CACHE_SCHEMA)

    def get(self, key: str) -> Any | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value, expires_epoch FROM api_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
            expires = row["expires_epoch"]
            if expires is not None and expires <= time.time():
                conn.execute(
                    "DELETE FROM api_cache WHERE cache_key = ?", (key,)
                )
                return None
        return json.loads(row["value"])

    def set(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        expires = (
            time.time() + ttl_seconds if ttl_seconds is not None else None
        )
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO api_cache (cache_key, value, expires_epoch)
                VALUES (?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    value         = excluded.value,
                    expires_epoch = excluded.expires_epoch
                """,
                (key, json.dumps(value), expires),
            )


# --- Resolved-account value object -------------------------------------------

@dataclass(frozen=True, slots=True)
class RiotAccount:
    """A resolved Riot identity — exactly the fields the resolver needs.

    A thin value object, not a normalized stats model: the api/ layer does
    no normalization. `puuid` is the stable cross-endpoint key; the resolver
    writes both fields onto the profile's SoloQ identity block.
    """
    puuid: str
    summoner_level: int


# --- Ranked-entry value object -----------------------------------------------

@dataclass(frozen=True, slots=True)
class RankedEntry:
    """One ranked queue entry from League-V4, reduced to scouting essentials.

    `queue_type` is Riot's canonical string ('RANKED_SOLO_5x5',
    'RANKED_FLEX_SR'). All other fields are copied verbatim from the API
    response — the api/ layer does not normalize tier labels or divisions.
    """
    queue_type: str   # e.g. 'RANKED_SOLO_5x5'
    tier: str         # e.g. 'DIAMOND'
    rank: str         # e.g. 'II'
    lp: int           # leaguePoints
    wins: int
    losses: int

    @property
    def games(self) -> int:
        return self.wins + self.losses

    @property
    def win_rate(self) -> float:
        """Fraction of games won; 0.0 for players with zero games."""
        return self.wins / self.games if self.games else 0.0


# --- Cache TTLs --------------------------------------------------------------
# A Riot-ID -> PUUID mapping is effectively permanent, so it is cached long.
# Summoner level only ever drifts upward, so a day-stale value is harmless.
# Ranked LP/tier shifts within hours during play, so one hour is a safe cap.
# Match payloads and timelines are immutable once a game ends — cache long.
# Match-id lists for a player must stay short-lived (new games keep arriving).

_ACCOUNT_CACHE_TTL    = 30 * 24 * 3600   # 30 days
_SUMMONER_CACHE_TTL   = 24 * 3600        # 24 hours
_RANKED_CACHE_TTL     =      3600        # 1 hour
_MATCH_IDS_CACHE_TTL  =      900         # 15 minutes
_MATCH_CACHE_TTL      = 30 * 24 * 3600   # 30 days (immutable post-game)
_TIMELINE_CACHE_TTL   = 30 * 24 * 3600   # 30 days (immutable post-game)


# --- The client --------------------------------------------------------------

class RiotClient:
    """Resolves Riot IDs to accounts via the Riot API (riotwatcher).

    Args:
        api_key: a Riot API key.
        cache:   optional read-through cache. Pass a `SqliteCacheStore` (or
                 any `CacheStore`) to avoid re-hitting the API; omit it for
                 an uncached client (e.g. in tests).
    """

    def __init__(self, api_key: str, cache: CacheStore | None = None) -> None:
        if not api_key:
            raise ValueError("api_key must be set.")
        self._riot = RiotWatcher(api_key)
        self._lol = LolWatcher(api_key)
        self._cache = cache

    # -- Public API ----------------------------------------------------------

    def fetch_ranked(self, puuid: str, platform: str) -> list[RankedEntry]:
        """Return all ranked queue entries for a player (League-V4 by_puuid).

        Args:
            puuid:    the player's PUUID, obtained from `resolve_account`.
            platform: a platform routing value, e.g. 'euw1'.

        Returns:
            A list of RankedEntry (typically 0–2 items: SoloQ and/or Flex).
            Returns an empty list if the player has no ranked games yet.

        Raises:
            ValueError: `platform` is not in PLATFORM_TO_REGION.
            ApiError:   any Riot API failure other than 404.
        """
        platform = platform.strip().lower()
        self._region_for(platform)   # validates; raises ValueError on bad input

        key = f"riot:ranked:{platform}:{puuid}"
        cached = self._cache_get(key)
        if cached is not None:
            return [RankedEntry(**e) for e in cached]

        try:
            entries = self._lol.league.by_puuid(platform, puuid)
        except ApiError as err:
            if _http_status(err) == 404:
                entries = []
            else:
                raise

        raw = [
            {
                "queue_type": e["queueType"],
                "tier":       e["tier"],
                "rank":       e["rank"],
                "lp":         e["leaguePoints"],
                "wins":       e["wins"],
                "losses":     e["losses"],
            }
            for e in entries
        ]
        self._cache_set(key, raw, _RANKED_CACHE_TTL)
        return [RankedEntry(**r) for r in raw]

    def resolve_account(self, riot_id: str, platform: str) -> RiotAccount:
        """Resolve a Riot ID to its PUUID and summoner level.

        Args:
            riot_id:  the player's Riot ID in 'GameName#TAG' form.
            platform: a platform routing value, e.g. 'euw1' (see
                      PLATFORM_TO_REGION for accepted values).

        Returns:
            A RiotAccount with the resolved PUUID and summoner level.

        Raises:
            LookupError: the Riot ID has no account, or the account has no
                         League summoner on `platform` (both are HTTP 404).
            ValueError:  `riot_id` is malformed or `platform` is unknown.
            ApiError:    any other Riot API failure (rate limit, auth, 5xx);
                         network errors propagate as their requests' type.
        """
        platform = platform.strip().lower()
        region = self._region_for(platform)
        game_name, tag_line = self._split_riot_id(riot_id)

        account = self._fetch_account(region, game_name, tag_line)
        summoner = self._fetch_summoner(platform, account["puuid"])

        return RiotAccount(
            puuid=account["puuid"],
            summoner_level=summoner["summonerLevel"],
        )

    def fetch_match_ids(
        self,
        puuid: str,
        platform: str,
        *,
        count: int = 20,
        queue: int = 420,
        start: int = 0,
        start_time: int | None = None,
    ) -> list[str]:
        """Return recent match IDs for a player (Match-V5 by-puuid/ids).

        Args:
            puuid:      the player's PUUID.
            platform:   a platform routing value, e.g. 'euw1'.
            count:      how many IDs to fetch (Riot caps at 100 per call).
            queue:      Riot queue ID. 420 = RANKED_SOLO_5x5. Pass 0 / falsy
                        to disable the queue filter (Match-V5 accepts the
                        absence of the parameter).
            start:      offset into the player's match history. Combine with
                        `count` to paginate (start=0, 100, 200, ...).
            start_time: epoch seconds — only matches AFTER this point are
                        returned. Required when scoping to a season; without
                        it Riot returns the player's all-time history.

        Returns: list of match IDs, newest first. Empty list when the
        player has no matching games in the window.
        """
        platform = platform.strip().lower()
        region = self._region_for(platform)
        key = (
            f"riot:match_ids:{region}:{puuid}:"
            f"{queue}:{count}:{start}:{start_time or 0}"
        )
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        kwargs: dict[str, Any] = {"start": start, "count": count}
        if queue:
            kwargs["queue"] = queue
        if start_time is not None:
            kwargs["start_time"] = start_time

        try:
            ids = self._lol.match.matchlist_by_puuid(region, puuid, **kwargs)
        except ApiError as err:
            if _http_status(err) == 404:
                ids = []
            else:
                raise
        ids = list(ids or [])
        self._cache_set(key, ids, _MATCH_IDS_CACHE_TTL)
        return ids

    def fetch_all_match_ids_since(
        self,
        puuid: str,
        platform: str,
        *,
        since_epoch: int,
        queue: int = 420,
        page_size: int = 100,
        hard_cap: int = 1000,
    ) -> list[str]:
        """Paginate `fetch_match_ids` to get every match ID after `since_epoch`.

        Riot caps each call at 100 IDs (`count<=100`); the API paginates via
        `start` offset. We keep paging until a short page comes back or
        `hard_cap` IDs collected — the latter guards against runaway loops
        if Riot's `start_time` filter were ever ignored.
        """
        out: list[str] = []
        start = 0
        while True:
            batch = self.fetch_match_ids(
                puuid, platform,
                count=page_size, queue=queue,
                start=start, start_time=since_epoch,
            )
            if not batch:
                break
            out.extend(batch)
            if len(batch) < page_size or len(out) >= hard_cap:
                break
            start += page_size
        return out[:hard_cap]

    def fetch_match(self, match_id: str, platform: str) -> dict[str, Any] | None:
        """Return the raw Match-V5 match DTO, or None if 404.

        Cached for 30 days because match data is immutable once a game
        ends — the same `match_id` will always return the same payload.
        """
        platform = platform.strip().lower()
        region = self._region_for(platform)
        key = f"riot:match:{region}:{match_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        try:
            match = self._lol.match.by_id(region, match_id)
        except ApiError as err:
            if _http_status(err) == 404:
                return None
            raise
        self._cache_set(key, match, _MATCH_CACHE_TTL)
        return match

    def fetch_match_timeline(
        self, match_id: str, platform: str,
    ) -> dict[str, Any] | None:
        """Return the raw Match-V5 timeline DTO, or None if 404.

        The timeline carries per-minute frames used to derive CS@10 and
        gold-diff @15 — kept in api/ as a passthrough; the derivation
        lives in `src/processing/match_stats.py`.
        """
        platform = platform.strip().lower()
        region = self._region_for(platform)
        key = f"riot:match_timeline:{region}:{match_id}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        try:
            timeline = self._lol.match.timeline_by_match(region, match_id)
        except ApiError as err:
            if _http_status(err) == 404:
                return None
            raise
        self._cache_set(key, timeline, _TIMELINE_CACHE_TTL)
        return timeline

    # -- Endpoint calls ------------------------------------------------------

    def _fetch_account(
        self, region: str, game_name: str, tag_line: str
    ) -> dict[str, Any]:
        """Account-V1: Riot ID -> account DTO (carries the PUUID)."""
        key = f"riot:account:{region}:{game_name.lower()}#{tag_line.lower()}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        try:
            account = self._riot.account.by_riot_id(region, game_name, tag_line)
        except ApiError as err:
            if _http_status(err) == 404:
                raise LookupError(
                    f"No Riot account for '{game_name}#{tag_line}' "
                    f"on routing region '{region}'."
                ) from err
            raise

        self._cache_set(key, account, _ACCOUNT_CACHE_TTL)
        return account

    def _fetch_summoner(self, platform: str, puuid: str) -> dict[str, Any]:
        """Summoner-V4: PUUID -> summoner DTO (carries the summoner level)."""
        key = f"riot:summoner:{platform}:{puuid}"
        cached = self._cache_get(key)
        if cached is not None:
            return cached

        try:
            summoner = self._lol.summoner.by_puuid(platform, puuid)
        except ApiError as err:
            if _http_status(err) == 404:
                raise LookupError(
                    f"Riot account resolved, but it has no League summoner "
                    f"on platform '{platform}'."
                ) from err
            raise

        self._cache_set(key, summoner, _SUMMONER_CACHE_TTL)
        return summoner

    # -- Cache helpers -------------------------------------------------------

    def _cache_get(self, key: str) -> Any | None:
        return self._cache.get(key) if self._cache is not None else None

    def _cache_set(self, key: str, value: Any, ttl_seconds: int) -> None:
        if self._cache is not None:
            self._cache.set(key, value, ttl_seconds)

    # -- Input parsing -------------------------------------------------------

    @staticmethod
    def _region_for(platform: str) -> str:
        try:
            return PLATFORM_TO_REGION[platform]
        except KeyError:
            known = ", ".join(sorted(PLATFORM_TO_REGION))
            raise ValueError(
                f"Unknown platform '{platform}'. Known platforms: {known}."
            ) from None

    @staticmethod
    def _split_riot_id(riot_id: str) -> tuple[str, str]:
        """Split 'GameName#TAG' into its game-name and tag-line parts."""
        game_name, sep, tag_line = riot_id.strip().partition("#")
        game_name, tag_line = game_name.strip(), tag_line.strip()
        if not sep or not game_name or not tag_line:
            raise ValueError(
                f"Riot ID '{riot_id}' must be in 'GameName#TAG' form."
            )
        return game_name, tag_line


# --- Helpers -----------------------------------------------------------------

def _http_status(err: ApiError) -> int | None:
    """Extract the HTTP status code from a riotwatcher ApiError, if present.

    riotwatcher's ApiError is a requests.HTTPError, so it carries the
    originating response; network-level failures are different exception
    types and never reach this helper.
    """
    response = getattr(err, "response", None)
    return getattr(response, "status_code", None)
