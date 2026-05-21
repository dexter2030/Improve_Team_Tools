"""Orchestrator pipeline'u: Leaguepedia -> lolpros -> Riot API -> SQLite."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from tqdm import tqdm

from .config import load_config, riot_api_key
from .database import Database
from .leaguepedia import fetch_all_players
from .lolpros import LolprosClient, find_lolpros_profile, normalize_slug
from .soloq import RiotClient, resolve_and_track

LOG = logging.getLogger(__name__)


def _setup_logging(log_path: str | Path) -> None:
    path = Path(log_path).resolve()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    already_attached = any(
        isinstance(h, logging.FileHandler)
        and getattr(h, "baseFilename", None) == str(path)
        for h in root.handlers
    )
    if not already_attached:
        handler = logging.FileHandler(path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        root.addHandler(handler)


@dataclass
class PipelineStats:
    players_fetched: int = 0
    lolpros_hits: int = 0
    riot_resolved: int = 0
    snapshots_saved: int = 0
    errors: int = 0


def _slug_url(nick: str) -> str:
    return f"https://lolpros.gg/player/{normalize_slug(nick)}"


def bootstrap(
    leagues: list[str] | None = None,
    active_since: datetime | None = None,
    config_path: str | Path | None = None,
    config: dict | None = None,
) -> PipelineStats:
    """Pełny przebieg dla świeżej bazy. Idempotentny — można puszczać wielokrotnie."""
    cfg = config or load_config(config_path)
    _setup_logging(cfg["paths"]["log"])
    user_agent = cfg["http"]["user_agent"]

    leagues = leagues or cfg["leagues"]
    if active_since is None:
        months = cfg.get("active_since_months", 12)
        active_since = datetime.utcnow() - timedelta(days=30 * months)

    LOG.info("=== bootstrap start leagues=%s since=%s ===", leagues, active_since.date())

    db = Database(cfg["paths"]["database"])
    stats = PipelineStats()

    try:
        riot = RiotClient(api_key=riot_api_key(), user_agent=user_agent)
    except RuntimeError as e:
        LOG.error("Riot API key missing: %s", e)
        db.close()
        raise

    players = fetch_all_players(
        leagues=leagues,
        active_since=active_since,
        user_agent=user_agent,
    )
    stats.players_fetched = len(players)
    LOG.info("Leaguepedia returned %d players", stats.players_fetched)

    lolpros = LolprosClient(
        user_agent=user_agent,
        delay_seconds=cfg["http"]["lolpros_delay_seconds"],
    )
    matches_count = cfg.get("matches_per_player", 20)
    queue = cfg.get("queue_ranked_solo", 420)

    for player in tqdm(players, desc="scouting"):
        try:
            accounts = find_lolpros_profile(player, lolpros)
            if accounts:
                stats.lolpros_hits += 1
                lolpros_url = _slug_url(player["nick"])
            else:
                lolpros_url = None
                LOG.info(
                    "no-lolpros: %s (%s / %s)",
                    player.get("nick"), player.get("league"), player.get("team"),
                )

            for acc in accounts:
                rid, tag, region = acc.get("riot_id"), acc.get("tag"), acc.get("region")
                if not rid or not tag or not region:
                    continue
                tracked = resolve_and_track(
                    rid, tag, region,
                    riot=riot,
                    matches_count=matches_count,
                    queue=queue,
                )
                if not tracked:
                    continue
                stats.riot_resolved += 1

                # zachowujemy poprzedni riot_id/tag w historii (DB samo zaloguje zmianę)
                db_data = {
                    **{k: v for k, v in player.items() if k != "page_name"},
                    "leaguepedia_page": player["page_name"],
                    "puuid": tracked["puuid"],
                    "riot_id": tracked["riot_id"],
                    "tag": tracked["tag"],
                    "region": tracked["platform"],
                    "lolpros_url": lolpros_url,
                }
                db.upsert_player(db_data)
                db.add_snapshot(tracked["puuid"], tracked)
                stats.snapshots_saved += 1
        except Exception as e:
            stats.errors += 1
            LOG.exception("Pipeline failure for %s: %s", player.get("nick"), e)

    LOG.info(
        "bootstrap done: fetched=%d lolpros=%d resolved=%d snapshots=%d errors=%d",
        stats.players_fetched,
        stats.lolpros_hits,
        stats.riot_resolved,
        stats.snapshots_saved,
        stats.errors,
    )
    db.close()
    return stats


def refresh_stale(
    days: int | None = None,
    config_path: str | Path | None = None,
    config: dict | None = None,
) -> PipelineStats:
    """Odśwież snapshoty graczy starszych niż `days`. Używaj cyklicznie (cron)."""
    cfg = config or load_config(config_path)
    _setup_logging(cfg["paths"]["log"])
    user_agent = cfg["http"]["user_agent"]
    days = days if days is not None else cfg.get("days_stale", 7)

    db = Database(cfg["paths"]["database"])
    riot = RiotClient(api_key=riot_api_key(), user_agent=user_agent)

    stale = db.get_players_for_refresh(days)
    LOG.info("refresh_stale: %d players older than %d days", len(stale), days)

    stats = PipelineStats()
    matches_count = cfg.get("matches_per_player", 20)
    queue = cfg.get("queue_ranked_solo", 420)

    for p in tqdm(stale, desc="refresh"):
        if not (p.get("riot_id_current") and p.get("tag_current") and p.get("region")):
            continue
        try:
            tracked = resolve_and_track(
                p["riot_id_current"], p["tag_current"], p["region"],
                riot=riot,
                matches_count=matches_count,
                queue=queue,
            )
            if not tracked:
                continue
            if tracked["puuid"] != p["puuid"]:
                LOG.warning(
                    "puuid mismatch for %s — riot_id changed account? db=%s api=%s",
                    p.get("nick"), p["puuid"], tracked["puuid"],
                )
                # Tworzymy nowy wpis pod nowym puuid, stary zostaje (historia).
            db.upsert_player({
                "puuid": tracked["puuid"],
                "leaguepedia_page": p.get("leaguepedia_page"),
                "nick": p.get("nick"),
                "team": p.get("team"),
                "role": p.get("role"),
                "country": p.get("country"),
                "residency": p.get("residency"),
                "league": p.get("league"),
                "lolpros_url": p.get("lolpros_url"),
                "riot_id": tracked["riot_id"],
                "tag": tracked["tag"],
                "region": tracked["platform"],
            })
            db.add_snapshot(tracked["puuid"], tracked)
            stats.snapshots_saved += 1
        except Exception as e:
            stats.errors += 1
            LOG.exception("refresh failed for %s: %s", p.get("nick"), e)

    LOG.info(
        "refresh_stale done: snapshots=%d errors=%d", stats.snapshots_saved, stats.errors
    )
    db.close()
    return stats


def add_manual_player(
    nick: str,
    riot_id: str,
    tag: str,
    region: str,
    role: str | None = None,
    team: str | None = None,
    league: str | None = None,
    country: str | None = None,
    config_path: str | Path | None = None,
    config: dict | None = None,
) -> dict | None:
    """Dodaj gracza spoza Leaguepedii — z pominięciem lolpros, prosto do Riot API."""
    cfg = config or load_config(config_path)
    _setup_logging(cfg["paths"]["log"])
    user_agent = cfg["http"]["user_agent"]

    db = Database(cfg["paths"]["database"])
    riot = RiotClient(api_key=riot_api_key(), user_agent=user_agent)

    tracked = resolve_and_track(
        riot_id, tag, region,
        riot=riot,
        matches_count=cfg.get("matches_per_player", 20),
        queue=cfg.get("queue_ranked_solo", 420),
    )
    if not tracked:
        LOG.warning("manual: nie udało się rozwiązać %s#%s na %s", riot_id, tag, region)
        db.close()
        return None

    db.upsert_player({
        "puuid": tracked["puuid"],
        "nick": nick,
        "team": team,
        "role": role,
        "country": country,
        "league": league,
        "riot_id": tracked["riot_id"],
        "tag": tracked["tag"],
        "region": tracked["platform"],
    })
    db.add_snapshot(tracked["puuid"], tracked)
    LOG.info("manual add: %s -> puuid=%s", nick, tracked["puuid"])
    db.close()
    return tracked


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Mini-przebieg do weryfikacji end-to-end — 2 małe ligi, ostatnie 3 mc.
    test_leagues = ["Ultraliga", "NLC"]
    since = datetime.utcnow() - timedelta(days=90)
    t0 = time.time()
    result = bootstrap(leagues=test_leagues, active_since=since)
    dt = time.time() - t0
    print("\n=== bootstrap finished ===")
    print(f"  duration:     {dt:.1f}s")
    print(f"  players:      {result.players_fetched}")
    print(f"  lolpros hits: {result.lolpros_hits} "
          f"({(result.lolpros_hits / result.players_fetched * 100 if result.players_fetched else 0):.1f}%)")
    print(f"  resolved:     {result.riot_resolved}")
    print(f"  snapshots:    {result.snapshots_saved}")
    print(f"  errors:       {result.errors}")
