"""
src/processing/cohort_baseline.py

Orchestracja: dla jednego konta SoloQ (z lolpros) pobiera mecze sezonu
z Riot API i liczy jeden wiersz baseline dla `soloq_baseline`.

Lives in `src/processing/`, bo to logika domenowa (filtry, dominująca
rola, redukcja meczy → metryki). Sam HTTP siedzi w `src/api/riot_client`.

Punkt wejścia: `compute_account_baseline(...)`. Pojedynczy try/except
łapie wszystkie błędy Riot API i zwraca `BaselineOutcome` z polem
`error` zamiast wybuchu — masowy fetch ma być odporny na padnięcie
jednego konta.
"""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Callable

from src.api.riot_client import RiotClient
from src.processing.match_stats import (
    MatchStats,
    aggregate_recent,
    compute_match_stats,
)

logger = logging.getLogger(__name__)

# Minimalna liczba mecz_w (SoloQ + Flex), żeby konto w_g_le uwzgl_dni_ — z
# pytania użytkownika („wszystkie konta na których jest zagrana 100 meczy").
DEFAULT_MIN_SEASON_GAMES = 100

# Hard cap na liczbę meczy / konto — chroni przed kontami z 1000+ gier,
# które wyssałyby rate-limit. 200 to z naddatkiem ponad próg 100.
DEFAULT_MAX_MATCHES = 200


@dataclass(frozen=True, slots=True)
class BaselineOutcome:
    """Wynik liczenia baseline dla jednego konta.

    `row` jest gotowy do upsert_soloq_baseline (dict). `status` to
    krótki kod:
      * "ok"         — policzono, row != None
      * "no_account" — Riot ID nie istnieje (404 z account-v1)
      * "skipped"    — konto nie spełnia progu min_games
      * "no_matches" — brak meczy SoloQ w oknie czasowym
      * "error"      — inny błąd (`error` ma wiadomość)
    """
    status: str
    row: dict | None
    error: str | None
    matches_fetched: int


def compute_account_baseline(
    *,
    overview_page: str,
    game_name: str,
    tag_line: str,
    platform: str,
    league: str | None,
    role_hint: str | None,
    since_epoch: int,
    riot_client: RiotClient,
    include_timeline: bool = True,
    min_season_games: int = DEFAULT_MIN_SEASON_GAMES,
    max_matches: int = DEFAULT_MAX_MATCHES,
    queue: int = 420,
    on_match: Callable[[int, int], None] | None = None,
) -> BaselineOutcome:
    """Liczy baseline dla jednego konta SoloQ.

    Args:
        overview_page:    Leaguepedia overview page (klucz join).
        game_name, tag_line, platform: identyfikatory Riot.
        league:           krótka nazwa ligi (do zapisu w baseline).
        role_hint:        rola z players_all (Top/Jungle/Mid/Bot/Support);
                          gdy w meczach inna dominuje, wygrywa ta z meczy.
        since_epoch:      cutoff sezonu (epoch seconds).
        riot_client:      shared client (z cache).
        include_timeline: True doda CS@10 / GD@15 (drugi call per mecz).
        min_season_games: konto z mniej grami SoloQ+Flex jest pomijane.
        max_matches:      hard cap na liczbę meczy / konto.
        queue:            Riot queue id (420 = SoloQ).
        on_match(i, n):   callback po każdym meczu — do paska postępu.
    """
    riot_id = f"{game_name}#{tag_line}"

    # 1) Resolve account → PUUID + level.
    try:
        account = riot_client.resolve_account(riot_id, platform)
    except LookupError:
        return BaselineOutcome("no_account", None, None, 0)
    except Exception as exc:
        return BaselineOutcome("error", None, f"resolve: {exc}", 0)

    # 2) Filter na bazie League-V4: skip kont z <min_season_games SoloQ.
    try:
        ranked = riot_client.fetch_ranked(account.puuid, platform)
    except Exception as exc:
        return BaselineOutcome("error", None, f"ranked: {exc}", 0)
    soloq_entry = next(
        (e for e in ranked if e.queue_type == "RANKED_SOLO_5x5"),
        None,
    )
    season_games = soloq_entry.games if soloq_entry else 0
    if season_games < min_season_games:
        return BaselineOutcome(
            "skipped", None,
            f"season games {season_games} < {min_season_games}",
            0,
        )

    # 3) Pull all match IDs since cutoff (paginated 100/call).
    try:
        match_ids = riot_client.fetch_all_match_ids_since(
            account.puuid, platform,
            since_epoch=since_epoch, queue=queue, hard_cap=max_matches,
            archival=True,
        )
    except Exception as exc:
        return BaselineOutcome("error", None, f"match_ids: {exc}", 0)
    if not match_ids:
        return BaselineOutcome("no_matches", None, None, 0)

    # 4) Per-match fetch + reduce.
    per_match: list[MatchStats] = []
    total = len(match_ids)
    for i, mid in enumerate(match_ids):
        try:
            match = riot_client.fetch_match(mid, platform)
        except Exception:
            match = None
        timeline = None
        if match and include_timeline:
            try:
                timeline = riot_client.fetch_match_timeline(mid, platform)
            except Exception:
                timeline = None
        if match:
            stats = compute_match_stats(match, timeline, account.puuid)
            if stats is not None:
                per_match.append(stats)
        if on_match is not None:
            on_match(i + 1, total)

    if not per_match:
        return BaselineOutcome("no_matches", None, None, 0)

    summary = aggregate_recent(per_match)
    dominant_role = _dominant_role(per_match) or _normalize_role(role_hint)

    row = {
        "overview_page": overview_page,
        "puuid":         account.puuid,
        "game_name":     game_name,
        "tag_line":      tag_line,
        "platform":      platform,
        "role":          dominant_role,
        "league":        league,
        "since_epoch":   int(since_epoch),
        "games":         summary.games,
        "winrate":       summary.winrate,
        "kda":           summary.kda,
        "cs_per_min":    summary.cs_per_min,
        "dpm":           summary.dpm,
        "gold_per_min":  summary.gold_per_min,
        "damage_taken_per_min": summary.damage_taken_per_min,
        "vision_per_min": summary.vision_per_min,
        "wards_per_min": summary.wards_per_min,
        "kp":            summary.kp,
        "cs10":          summary.cs10,
        "gd15":          summary.gd15,
        "solo_kills":    summary.solo_kills,
        "first_blood_rate": summary.first_blood_rate,
        "tier":          soloq_entry.tier if soloq_entry else None,
        "rank":          soloq_entry.rank if soloq_entry else None,
        "lp":            soloq_entry.lp if soloq_entry else None,
        "payload":       {
            "summoner_level": account.summoner_level,
            "season_games_total": season_games,
        },
    }
    return BaselineOutcome("ok", row, None, len(per_match))


def _dominant_role(stats: list[MatchStats]) -> str | None:
    """Najczęstsza niepusta rola w oknie meczy.

    Riot zwraca TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY w teamPosition. Mapujemy
    je na nasze nazwy z draft_analyzer (Top/Jungle/Mid/Bot/Support) tylko
    przy zapisie do baseline — łatwiej filtrować w UI.
    """
    counts = Counter(s.role for s in stats if s.role)
    if not counts:
        return None
    most_common, _ = counts.most_common(1)[0]
    return _normalize_role(most_common)


_ROLE_MAP: dict[str, str] = {
    "TOP":     "Top",
    "JUNGLE":  "Jungle",
    "MIDDLE":  "Mid",
    "MID":     "Mid",
    "BOTTOM":  "Bot",
    "BOT":     "Bot",
    "ADC":     "Bot",
    "UTILITY": "Support",
    "SUPPORT": "Support",
}


def _normalize_role(role: str | None) -> str | None:
    if not role:
        return None
    return _ROLE_MAP.get(role.strip().upper(), role)
