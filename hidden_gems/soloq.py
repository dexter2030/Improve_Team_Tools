"""
hidden_gems/soloq.py

Wspólny interfejs do danych soloQ z dwoma wymiennymi implementacjami:
- RiotProvider:  ŹRÓDŁO GŁÓWNE. Riot API (account-v1, league-v4, match-v5)
                 — przez WSPÓLNY `src/api/riot_client.py` (cache,
                 rate-limit, region routing) + `src/processing/match_stats`.
- OpggProvider:  ŹRÓDŁO ZAPASOWE. Scrapuje agregaty z OP.GG.

Oba zgodne z Protocol `SoloQProvider` — UI może operować na "jakimś" providerze
i przełączać go po cichu, jeśli główne źródło zawiedzie.

Klucz Riot WYŁĄCZNIE z env: RIOT_API_KEY (nigdy w kodzie).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol

import requests

from src.api.riot_client import RiotClient, SqliteCacheStore
from src.processing.match_stats import aggregate_recent, compute_match_stats

logger = logging.getLogger(__name__)


# --- Typy zwrotne -----------------------------------------------------------

@dataclass(frozen=True)
class RankInfo:
    """Wynik get_rank — ranga, LP i statystyki rankingowe."""
    tier:     str | None     # "EMERALD", "DIAMOND", "MASTER", "UNRANKED", ...
    division: str | None     # "I"–"IV"; None dla MASTER+ i UNRANKED
    lp:       int | None
    winrate:  float | None
    games:    int | None


@dataclass(frozen=True)
class RecentPerformance:
    """Wynik get_recent_performance — średnia z ostatnich N meczów rank."""
    games:      int
    kda:        float | None
    cs_per_min: float | None
    dpm:        float | None
    kp:         float | None
    cs_at_10:   float | None  # tylko RiotProvider (liczone z timeline)
    gd_at_15:   float | None  # tylko RiotProvider (liczone z timeline)


class SoloQProvider(Protocol):
    """Kontrakt, który spełniają oba providery."""

    def get_rank(self, riot_id: str, region: str) -> RankInfo | None: ...

    def get_recent_performance(
        self, riot_id: str, region: str, n: int = 20,
    ) -> RecentPerformance | None: ...


# --- RiotProvider -----------------------------------------------------------

class RiotProvider:
    """Cienki adapter nad wspólnym `src/api/riot_client.RiotClient`.

    Cała logika HTTP (rate limit 20/s + 100/2min, retry 429 z Retry-After,
    cache odpowiedzi przez SqliteCacheStore, region routing) siedzi we
    wspólnym kliencie — tu zostaje wyłącznie mapowanie wyniku na typy
    `RankInfo` / `RecentPerformance` używane przez `scoring.py`.

    Współdzielenie cache: domyślnie używamy tej samej `scouting.db` co
    reszta projektu — odpowiedzi Riot API serwujemy z cache między
    wywołaniami z różnych miejsc (resolver, UI, scoring).
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        client: RiotClient | None = None,
        db_path: str | None = None,
    ) -> None:
        if client is not None:
            self._client = client
            return
        api_key = api_key or os.environ.get("RIOT_API_KEY", "")
        if not api_key:
            raise RuntimeError(
                "RIOT_API_KEY nie ustawiony. Dodaj do .env: "
                "RIOT_API_KEY=RGAPI-..."
            )
        cache = SqliteCacheStore(db_path or "scouting.db")
        self._client = RiotClient(api_key, cache=cache)

    # -- API -----------------------------------------------------------------

    def get_rank(self, riot_id: str, region: str) -> RankInfo | None:
        try:
            entries = self._fetch_ranked_entries(riot_id, region)
        except RuntimeError as exc:
            logger.warning("Riot get_rank fail dla %s: %s", riot_id, exc)
            return None
        if entries is None:
            return None

        for e in entries:
            if e.queue_type != "RANKED_SOLO_5x5":
                continue
            games = e.wins + e.losses
            return RankInfo(
                tier=e.tier,
                division=e.rank,
                lp=e.lp,
                winrate=(e.wins / games) if games else None,
                games=games,
            )
        return RankInfo(tier="UNRANKED", division=None,
                        lp=None, winrate=None, games=0)

    def get_recent_performance(
        self, riot_id: str, region: str, n: int = 20,
    ) -> RecentPerformance | None:
        try:
            puuid = self._resolve_puuid(riot_id, region)
        except RuntimeError as exc:
            logger.warning("Riot get_recent_performance fail %s: %s", riot_id, exc)
            return None
        if puuid is None:
            return None

        try:
            ids = self._client.fetch_match_ids(puuid, region, count=n, queue=420)
        except Exception as exc:
            logger.warning("Riot fetch_match_ids fail %s: %s", riot_id, exc)
            return None
        if not ids:
            return None

        per_match = []
        for mid in ids:
            try:
                match = self._client.fetch_match(mid, region)
            except Exception as exc:
                logger.warning("Riot fetch_match %s fail: %s", mid, exc)
                continue
            if not match:
                continue
            try:
                timeline = self._client.fetch_match_timeline(mid, region)
            except Exception as exc:
                logger.warning("Riot timeline %s fail: %s", mid, exc)
                timeline = None
            stats = compute_match_stats(match, timeline, puuid)
            if stats is not None:
                per_match.append(stats)

        if not per_match:
            return None

        agg = aggregate_recent(per_match)
        return RecentPerformance(
            games=agg.games,
            kda=agg.kda,
            cs_per_min=agg.cs_per_min,
            dpm=agg.dpm,
            kp=agg.kp,
            cs_at_10=agg.cs10,
            gd_at_15=agg.gd15,
        )

    # -- Internals -----------------------------------------------------------

    def _resolve_puuid(self, riot_id: str, region: str) -> str | None:
        if "#" not in riot_id:
            logger.warning("Riot ID musi być w formacie Name#TAG: %r", riot_id)
            return None
        try:
            account = self._client.resolve_account(riot_id, region)
        except LookupError:
            return None
        return account.puuid

    def _fetch_ranked_entries(self, riot_id: str, region: str):
        """Zwraca listę RankedEntry albo None gdy konto nieznane."""
        puuid = self._resolve_puuid(riot_id, region)
        if puuid is None:
            return None
        return self._client.fetch_ranked(puuid, region)


# --- OpggProvider -----------------------------------------------------------

class OpggProvider:
    """Scrapuje agregaty z OP.GG.

    UWAGA: To jest scraping krytyczny na zmiany layoutu OP.GG. Wyciągamy dane
    z osadzonego JSON-a (`<script id="__NEXT_DATA__">`) — stabilniejsze niż
    DOM, ale wciąż NIE jest to oficjalne API. Każdy fetch jest opakowany w
    try/except; przy jakimkolwiek błędzie zwracamy None — UI ma się
    przełączyć na RiotProvider.

    CS@10 / GD@15 nie są dostępne w łatwym formacie z OP.GG — te dwie metryki
    zwracane są zawsze jako None. Pełne lane performance tylko z Riota.
    """

    _BASE = "https://www.op.gg/summoners/{platform}/{slug}"
    _UA = (
        "Mozilla/5.0 (compatible; lol-scouting-hidden-gems/0.1; "
        "research)"
    )

    def __init__(self, timeout: int = 15) -> None:
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": self._UA})

    def get_rank(self, riot_id: str, region: str) -> RankInfo | None:
        page = self._fetch_page(riot_id, region)
        if page is None:
            return None
        try:
            data = _extract_next_data(page)
            summoner = _deep_first(data, "summoner") or {}
            league_stats = summoner.get("league_stats") or []
            soloq = next(
                (
                    s for s in league_stats
                    if (s.get("queue_info") or {}).get("game_type")
                    == "SOLORANKED"
                ),
                league_stats[0] if league_stats else None,
            )
            if not soloq:
                return None
            tier_info = soloq.get("tier_info") or {}
            wins, losses = soloq.get("win", 0), soloq.get("lose", 0)
            games = wins + losses
            return RankInfo(
                tier=tier_info.get("tier"),
                division=tier_info.get("division"),
                lp=tier_info.get("lp"),
                winrate=(wins / games) if games else None,
                games=games,
            )
        except Exception as exc:
            logger.warning("OP.GG: rank parse fail dla %s: %s", riot_id, exc)
            return None

    def get_recent_performance(
        self, riot_id: str, region: str, n: int = 20,
    ) -> RecentPerformance | None:
        page = self._fetch_page(riot_id, region)
        if page is None:
            return None
        try:
            data = _extract_next_data(page)
            # OP.GG bywa kapryśny w nazwach — sprawdzamy kilka.
            stats = (
                _deep_first(data, "recent_stats")
                or _deep_first(data, "stats")
                or {}
            )
            games = (
                stats.get("games")
                or stats.get("game_count")
                or stats.get("count")
                or 0
            )
            return RecentPerformance(
                games=int(games),
                kda=_to_float(stats.get("kda")),
                cs_per_min=_to_float(
                    stats.get("cs_per_min")
                    or stats.get("minion_kills_per_min")
                ),
                dpm=_to_float(
                    stats.get("damage_per_min")
                    or stats.get("dpm")
                ),
                kp=_to_float(
                    stats.get("kill_participation")
                    or stats.get("kp")
                ),
                cs_at_10=None,
                gd_at_15=None,
            )
        except Exception as exc:
            logger.warning("OP.GG: perf parse fail dla %s: %s", riot_id, exc)
            return None

    def _fetch_page(self, riot_id: str, region: str) -> str | None:
        if "#" not in riot_id:
            logger.warning("OP.GG: Riot ID musi mieć format Name#TAG")
            return None
        slug = riot_id.replace("#", "-")
        url = self._BASE.format(platform=region.lower(), slug=slug)
        try:
            r = self._session.get(url, timeout=self._timeout)
        except requests.RequestException as exc:
            logger.warning("OP.GG GET fail %s: %s", url, exc)
            return None
        if r.status_code != 200:
            logger.warning("OP.GG %d %s", r.status_code, url)
            return None
        return r.text


def _extract_next_data(html: str) -> dict:
    """Wyciąga osadzony JSON z <script id="__NEXT_DATA__">.

    Next.js'owy state strony — stabilniejszy niż HTML, ale nie API.
    """
    m = re.search(
        r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        raise ValueError("Brak __NEXT_DATA__ w HTML")
    return json.loads(m.group(1))


def _deep_first(obj: Any, key: str) -> Any | None:
    """BFS przez dict/listy — pierwsza wartość pod kluczem `key`."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _deep_first(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _deep_first(v, key)
            if r is not None:
                return r
    return None


def _to_float(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- Przykład użycia --------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        riot = RiotProvider()
        print("== Riot.get_rank ==")
        print(riot.get_rank("Caps#EUW", "euw1"))
        print("\n== Riot.get_recent_performance (n=5) ==")
        print(riot.get_recent_performance("Caps#EUW", "euw1", n=5))
    except RuntimeError as exc:
        print(f"[Riot pominięty] {exc}")

    print("\n== OP.GG.get_rank ==")
    opgg = OpggProvider()
    print(opgg.get_rank("Caps#EUW", "euw1"))
    print("\n== OP.GG.get_recent_performance ==")
    print(opgg.get_recent_performance("Caps#EUW", "euw1"))
