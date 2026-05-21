"""
src/cache/profile_store.py

SQLite-backed persistence for ScoutingProfile objects.

Profiles are NOT cache entries — they never expire and are hand-curated,
so they live in their own table. The same .db file can also hold the
API response cache (separate table), keeping deployment to a single file.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from src.processing.profiles import Role, ScoutingProfile

_SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    profile_id        TEXT PRIMARY KEY,
    display_name      TEXT NOT NULL,
    role              TEXT NOT NULL,
    resolution_state  TEXT NOT NULL,
    updated_utc       TEXT NOT NULL,
    payload           TEXT NOT NULL   -- full profile as JSON
);
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role);
"""


class ProfileStore:
    """CRUD layer for scouting profiles, backed by a single SQLite file."""

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
            conn.executescript(_SCHEMA)

    # -- Write ---------------------------------------------------------------

    def upsert(self, profile: ScoutingProfile) -> None:
        """Insert a new profile or overwrite an existing one by profile_id."""
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO profiles
                    (profile_id, display_name, role, resolution_state,
                     updated_utc, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(profile_id) DO UPDATE SET
                    display_name     = excluded.display_name,
                    role             = excluded.role,
                    resolution_state = excluded.resolution_state,
                    updated_utc      = excluded.updated_utc,
                    payload          = excluded.payload
                """,
                (
                    profile.profile_id,
                    profile.display_name,
                    profile.role.value,
                    profile.resolution_state.value,
                    profile.updated_utc,
                    json.dumps(profile.to_dict()),
                ),
            )

    def delete(self, profile_id: str) -> bool:
        """Remove a profile. Returns True if a row was deleted."""
        with self._conn() as conn:
            cur = conn.execute(
                "DELETE FROM profiles WHERE profile_id = ?", (profile_id,)
            )
            return cur.rowcount > 0

    # -- Read ----------------------------------------------------------------

    def get(self, profile_id: str) -> ScoutingProfile | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT payload FROM profiles WHERE profile_id = ?",
                (profile_id,),
            ).fetchone()
        if row is None:
            return None
        return ScoutingProfile.from_dict(json.loads(row["payload"]))

    def list_all(self, role: Role | None = None) -> list[ScoutingProfile]:
        """Return all profiles, optionally filtered to a single role."""
        query = "SELECT payload FROM profiles"
        params: tuple[str, ...] = ()
        if role is not None:
            query += " WHERE role = ?"
            params = (role.value,)
        query += " ORDER BY updated_utc DESC"
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            ScoutingProfile.from_dict(json.loads(r["payload"])) for r in rows
        ]

    def count(self) -> int:
        with self._conn() as conn:
            return conn.execute(
                "SELECT COUNT(*) AS n FROM profiles"
            ).fetchone()["n"]
