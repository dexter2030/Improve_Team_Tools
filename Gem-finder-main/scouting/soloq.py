"""KROK 3 pipeline'u: riot_id+tag -> puuid -> ranga + staty meczowe.

Cała warstwa HTTP/limiter/region-routing/cache została scalona ze wspólnym
`src/api/riot_client.py`. Tutaj zostaje:
  * mapa aliasów regionów ("EUW" -> "EUW1") których używa lolpros.gg
    — Riot dev API tego nie akceptuje, więc normalizujemy przed wołaniem;
  * orkiestracja `resolve_and_track`: konto -> ranga -> średnie z N meczów
    (przez wspólne `compute_match_stats` z `src/processing/match_stats`).

Klasa `RiotClient` to cienki wrapper na `src.api.riot_client.RiotClient`,
zachowany dla zgodności wywołań `RiotClient(api_key=..., user_agent=...)`
z `pipeline.py`. `user_agent` jest ignorowany — riotwatcher ustawia własny.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from src.api.riot_client import RiotClient as _SharedRiotClient
from src.api.riot_client import SqliteCacheStore
from src.processing.match_stats import compute_match_stats

LOG = logging.getLogger(__name__)


# Aliasy używane na lolpros.gg / kasualnie -> Riot platform IDs.
# Wspólny `src/api/riot_client.py` operuje na platform IDs ("euw1") — tu
# normalizujemy zewnętrzne formy ("EUW", "OCE") zanim pójdą do klienta.
REGION_ALIASES = {
    "EUW": "EUW1", "EUNE": "EUN1", "NA": "NA1", "BR": "BR1",
    "LAN": "LA1", "LAS": "LA2", "OCE": "OC1", "TR": "TR1",
    "JP": "JP1", "PH": "PH2", "SG": "SG2", "TH": "TH2", "TW": "TW2", "VN": "VN2",
}


def normalize_platform(region: str) -> str:
    """Mapuje krótkie aliasy (EUW, OCE...) na Riot platform ID (EUW1, OC1...)."""
    r = region.upper().strip()
    return REGION_ALIASES.get(r, r)


class RiotClient(_SharedRiotClient):
    """Wrapper na wspólny RiotClient, kompatybilny z wywołaniami z pipeline.py.

    pipeline.py konstruuje klient jako `RiotClient(api_key=..., user_agent=...)`.
    Wspólny klient nie zna `user_agent` (riotwatcher trzyma własny UA), więc
    łykamy ten argument i tworzymy domyślny `SqliteCacheStore` na ścieżce
    `scouting.db` w bieżącym katalogu (taki sam plik, którego używa cała
    aplikacja — cache odpowiedzi serwuje się wielu konsumentom).
    """

    def __init__(
        self,
        api_key: str,
        user_agent: str = "gem-finder/0.1",   # ignorowany, dla zgodności
        *,
        db_path: str = "scouting.db",
    ) -> None:
        super().__init__(api_key, cache=SqliteCacheStore(db_path))


def resolve_and_track(
    riot_id: str,
    tag: str,
    region: str,
    riot: RiotClient,
    matches_count: int = 20,
    queue: int = 420,
) -> dict | None:
    """Riot ID+tag -> puuid + ranga + uśrednione staty z N meczów soloQ.

    Zwraca dict gotowy do zapisu w bazie (kolumny tabeli `players` +
    `soloq_snapshots`) albo None, jeśli konto nie istnieje.
    """
    platform = normalize_platform(region)
    full_riot_id = f"{riot_id}#{tag}"

    try:
        account = riot.resolve_account(full_riot_id, platform)
    except LookupError:
        LOG.info("Riot: brak konta dla %s (%s)", full_riot_id, region)
        return None
    except ValueError as exc:
        LOG.warning("Riot: nieprawidłowy region/Riot ID — %s", exc)
        return None

    puuid = account.puuid

    # Ranga: lecimy bezpośrednio przez wspólny league-v4 helper.
    rank_str: str | None = None
    lp = wins = losses = 0
    winrate: float | None = None
    try:
        entries = riot.fetch_ranked(puuid, platform)
    except Exception as exc:
        LOG.warning("Riot league entries fail puuid=%s: %s", puuid, exc)
        entries = []
    solo = next((e for e in entries if e.queue_type == "RANKED_SOLO_5x5"), None)
    if solo is not None:
        rank_str = f"{solo.tier} {solo.rank}".strip()
        lp = solo.lp
        wins, losses = solo.wins, solo.losses
        if wins + losses > 0:
            winrate = round(wins / (wins + losses), 3)

    # Statystyki meczowe — N ostatnich rankingowych.
    try:
        ids = riot.fetch_match_ids(puuid, platform, count=matches_count, queue=queue)
    except Exception as exc:
        LOG.warning("Riot match ids fail puuid=%s: %s", puuid, exc)
        ids = []

    per_match: list[Any] = []
    for mid in ids:
        try:
            match = riot.fetch_match(mid, platform)
        except Exception as exc:
            LOG.warning("Riot match %s fail: %s", mid, exc)
            continue
        if not match:
            continue
        try:
            timeline = riot.fetch_match_timeline(mid, platform)
        except Exception as exc:
            LOG.warning("Riot timeline %s fail: %s", mid, exc)
            timeline = None
        stats = compute_match_stats(match, timeline, puuid)
        if stats is not None:
            per_match.append(stats)

    def _avg(attr: str) -> float | None:
        vals = [getattr(s, attr) for s in per_match
                if getattr(s, attr) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    # Account-V1 nie ma `gameName`/`tagLine` w naszym `RiotAccount` —
    # wspólny `resolve_account` zwraca tylko puuid + summoner_level.
    # Dla bazy zachowujemy oryginalny riot_id / tag (Riot je akceptował,
    # więc są stabilne aż do zmiany nicku przez gracza).
    return {
        "puuid": puuid,
        "riot_id": riot_id,
        "tag": tag,
        "platform": platform,
        "summoner_level": account.summoner_level,
        "rank": rank_str,
        "lp": lp,
        "wins": wins,
        "losses": losses,
        "winrate": winrate,
        "games": wins + losses,
        "kda": _avg("kda"),
        "cs_per_min": _avg("cs_per_min"),
        "dpm": _avg("dpm"),
        "kp": _avg("kp"),
        "cs10": _avg("cs10"),
        "gd15": _avg("gd15"),
        "matches_analyzed": len(per_match),
        "snapshot_ts": int(time.time()),
    }
