"""Warstwa SQLite — players + snapshoty soloQ + benchmarki ligowe."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    puuid               TEXT PRIMARY KEY,
    leaguepedia_page    TEXT,
    nick                TEXT,
    team                TEXT,
    role                TEXT,
    country             TEXT,
    residency           TEXT,
    league              TEXT,
    lolpros_url         TEXT,
    riot_id_current     TEXT,
    tag_current         TEXT,
    region              TEXT,
    last_updated        INTEGER,
    extra_json          TEXT
);

CREATE INDEX IF NOT EXISTS idx_players_leaguepedia ON players(leaguepedia_page);
CREATE INDEX IF NOT EXISTS idx_players_league      ON players(league);
CREATE INDEX IF NOT EXISTS idx_players_last_upd    ON players(last_updated);

CREATE TABLE IF NOT EXISTS soloq_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    puuid               TEXT NOT NULL,
    snapshot_date       INTEGER NOT NULL,
    rank                TEXT,
    lp                  INTEGER,
    winrate             REAL,
    games               INTEGER,
    kda                 REAL,
    cs_per_min          REAL,
    dpm                 REAL,
    kp                  REAL,
    cs10                REAL,
    gd15                REAL,
    matches_analyzed    INTEGER,
    FOREIGN KEY (puuid) REFERENCES players(puuid)
);

CREATE INDEX IF NOT EXISTS idx_snapshots_puuid_date
    ON soloq_snapshots(puuid, snapshot_date);

CREATE TABLE IF NOT EXISTS league_benchmarks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    league          TEXT NOT NULL,
    role            TEXT NOT NULL,
    metric          TEXT NOT NULL,
    value           REAL,
    calculated_at   INTEGER,
    UNIQUE (league, role, metric, calculated_at)
);

CREATE TABLE IF NOT EXISTS riot_id_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    puuid       TEXT NOT NULL,
    riot_id     TEXT,
    tag         TEXT,
    region      TEXT,
    seen_at     INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_riot_history_puuid ON riot_id_history(puuid);
"""

_PLAYER_CORE_FIELDS = {
    "puuid", "leaguepedia_page", "nick", "team", "role", "country",
    "residency", "league", "lolpros_url", "riot_id", "tag", "region",
}


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON;")
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    @contextmanager
    def tx(self):
        try:
            yield self._conn
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise

    # ---- players ----

    def upsert_player(self, data: dict) -> None:
        if not data.get("puuid"):
            raise ValueError("upsert_player wymaga puuid")
        now = int(time.time())

        cur = self._conn.execute(
            "SELECT riot_id_current, tag_current FROM players WHERE puuid = ?",
            (data["puuid"],),
        )
        existing = cur.fetchone()
        new_riot = data.get("riot_id")
        new_tag = data.get("tag")
        if existing and new_riot and (
            existing["riot_id_current"] != new_riot or existing["tag_current"] != new_tag
        ):
            self._conn.execute(
                "INSERT INTO riot_id_history (puuid, riot_id, tag, region, seen_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (data["puuid"], existing["riot_id_current"], existing["tag_current"],
                 data.get("region"), now),
            )

        extras = {k: v for k, v in data.items() if k not in _PLAYER_CORE_FIELDS}
        self._conn.execute(
            """
            INSERT INTO players (
                puuid, leaguepedia_page, nick, team, role, country, residency,
                league, lolpros_url, riot_id_current, tag_current, region,
                last_updated, extra_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(puuid) DO UPDATE SET
                leaguepedia_page = COALESCE(excluded.leaguepedia_page, players.leaguepedia_page),
                nick             = COALESCE(excluded.nick,             players.nick),
                team             = COALESCE(excluded.team,             players.team),
                role             = COALESCE(excluded.role,             players.role),
                country          = COALESCE(excluded.country,          players.country),
                residency        = COALESCE(excluded.residency,        players.residency),
                league           = COALESCE(excluded.league,           players.league),
                lolpros_url      = COALESCE(excluded.lolpros_url,      players.lolpros_url),
                riot_id_current  = COALESCE(excluded.riot_id_current,  players.riot_id_current),
                tag_current      = COALESCE(excluded.tag_current,      players.tag_current),
                region           = COALESCE(excluded.region,           players.region),
                last_updated     = excluded.last_updated,
                extra_json       = COALESCE(excluded.extra_json,       players.extra_json)
            """,
            (
                data["puuid"],
                data.get("leaguepedia_page"),
                data.get("nick"),
                data.get("team"),
                data.get("role"),
                data.get("country"),
                data.get("residency"),
                data.get("league"),
                data.get("lolpros_url"),
                new_riot,
                new_tag,
                data.get("region"),
                now,
                json.dumps(extras) if extras else None,
            ),
        )
        self._conn.commit()

    def add_snapshot(self, puuid: str, stats: dict) -> None:
        self._conn.execute(
            """
            INSERT INTO soloq_snapshots (
                puuid, snapshot_date, rank, lp, winrate, games,
                kda, cs_per_min, dpm, kp, cs10, gd15, matches_analyzed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                puuid,
                stats.get("snapshot_ts") or int(time.time()),
                stats.get("rank"),
                stats.get("lp"),
                stats.get("winrate"),
                stats.get("games"),
                stats.get("kda"),
                stats.get("cs_per_min"),
                stats.get("dpm"),
                stats.get("kp"),
                stats.get("cs10"),
                stats.get("gd15"),
                stats.get("matches_analyzed"),
            ),
        )
        self._conn.commit()

    def get_player(self, puuid: str) -> dict | None:
        cur = self._conn.execute("SELECT * FROM players WHERE puuid = ?", (puuid,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_player_by_leaguepedia(self, page: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT * FROM players WHERE leaguepedia_page = ?", (page,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_players_for_refresh(self, older_than_days: int) -> list[dict]:
        """Gracze, których ostatni snapshot jest starszy niż N dni (lub nigdy nie był)."""
        threshold = int(time.time()) - older_than_days * 86400
        cur = self._conn.execute(
            """
            SELECT p.* FROM players p
            LEFT JOIN (
                SELECT puuid, MAX(snapshot_date) AS last_snap
                FROM soloq_snapshots
                GROUP BY puuid
            ) s ON s.puuid = p.puuid
            WHERE s.last_snap IS NULL OR s.last_snap < ?
            ORDER BY COALESCE(s.last_snap, 0) ASC
            """,
            (threshold,),
        )
        return [dict(r) for r in cur.fetchall()]

    def all_players(self) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM players ORDER BY league, role, nick"
        )
        return [dict(r) for r in cur.fetchall()]

    def latest_snapshot(self, puuid: str) -> dict | None:
        cur = self._conn.execute(
            "SELECT * FROM soloq_snapshots WHERE puuid = ? "
            "ORDER BY snapshot_date DESC LIMIT 1",
            (puuid,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def snapshots_for(self, puuid: str) -> list[dict]:
        cur = self._conn.execute(
            "SELECT * FROM soloq_snapshots WHERE puuid = ? "
            "ORDER BY snapshot_date ASC",
            (puuid,),
        )
        return [dict(r) for r in cur.fetchall()]
