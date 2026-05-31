"""
scripts/migrate_dbs.py — jednorazowa migracja do baz per domena.

Przenosi wiersze z dawnej topologii (jeden `scouting.db` = profiles+api_cache,
jeden `drafts.db` = drafty+gracze+kohorta) do pięciu plików per domena w
``data/`` (profiles / cache / drafts / players / cohort).

Własności:
- IDEMPOTENTNY — ``INSERT OR IGNORE`` po kluczu głównym; ponowne uruchomienie
  nie duplikuje danych.
- NIGDY nie kasuje plików źródłowych — to jest rollback.
- Asercja ``COUNT(*)`` cel >= źródło dla każdej tabeli; rozbieżność => błąd.
- Kopiuje tylko kolumny wspólne dla źródła i celu (odporne na drift schematu).

Uruchom (z katalogu apps/streamlit-dashboard, interpreter z .venv):
    ..\\..\\.venv\\Scripts\\python.exe scripts\\migrate_dbs.py
opcjonalnie z jawnymi źródłami:
    ... scripts\\migrate_dbs.py --src-scouting <path> --src-drafts <path>
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# --- bootstrap sys.path: app root + packages/shared ---
_APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_APP_ROOT))
_shared = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
) / "packages" / "shared"
sys.path.insert(0, str(_shared))

from src.paths import CACHE_DB, COHORT_DB, DRAFTS_DB, PLAYERS_DB, PROFILES_DB  # noqa: E402
from src.cache.profile_store import ProfileStore  # noqa: E402
from shared.api.riot_client import SqliteCacheStore  # noqa: E402
from draft_analyzer import db as draft_db  # noqa: E402

_REPO_ROOT = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
)

# target -> (źródło, [tabele])
PLAN = [
    (PROFILES_DB, "scouting", ["profiles"]),
    (CACHE_DB, "scouting", ["api_cache"]),
    (DRAFTS_DB, "drafts", ["drafts", "league_sync"]),
    (PLAYERS_DB, "drafts", ["players", "players_sync", "players_all", "players_all_sync"]),
    (COHORT_DB, "drafts", ["lolpros_accounts", "soloq_baseline"]),
]


def _columns(conn: sqlite3.Connection, table: str, schema: str = "main") -> list[str]:
    rows = conn.execute(f'PRAGMA {schema}.table_info("{table}")').fetchall()
    return [r[1] for r in rows]


def _table_exists(conn: sqlite3.Connection, table: str, schema: str = "main") -> bool:
    q = f"SELECT 1 FROM {schema}.sqlite_master WHERE type='table' AND name=?"
    return conn.execute(q, (table,)).fetchone() is not None


def _count(conn: sqlite3.Connection, table: str, schema: str = "main") -> int:
    return conn.execute(f'SELECT COUNT(*) FROM {schema}."{table}"').fetchone()[0]


def _ensure_target_schemas() -> None:
    """Tworzy schematy docelowe (CREATE IF NOT EXISTS) zanim cokolwiek kopiujemy."""
    draft_db.init_db()              # drafts.db + players.db + cohort.db
    ProfileStore(PROFILES_DB)       # profiles.db
    SqliteCacheStore(CACHE_DB)      # cache.db


def migrate(src_scouting: Path, src_drafts: Path) -> bool:
    sources = {"scouting": src_scouting, "drafts": src_drafts}
    print("Źródła:")
    for k, p in sources.items():
        print(f"  {k:9} {p}  ({'OK' if p.exists() else 'BRAK'})")
    print("Cele (data/):")
    for tgt, _, _ in PLAN:
        print(f"  {tgt}")
    print()

    _ensure_target_schemas()

    ok = True
    for target_db, src_key, tables in PLAN:
        src = sources[src_key]
        conn = sqlite3.connect(target_db)
        try:
            conn.execute("ATTACH DATABASE ? AS src", (str(src),))
            for t in tables:
                if not _table_exists(conn, t, "src"):
                    print(f"  [skip] {t:20} (brak w źródle — tworzona pusta w celu)")
                    continue
                src_cols = _columns(conn, t, "src")
                tgt_cols = _columns(conn, t, "main")
                common = [c for c in tgt_cols if c in src_cols]
                collist = ", ".join(f'"{c}"' for c in common)
                conn.execute(
                    f'INSERT OR IGNORE INTO main."{t}" ({collist}) '
                    f'SELECT {collist} FROM src."{t}"'
                )
                conn.commit()
                n_src = _count(conn, t, "src")
                n_tgt = _count(conn, t, "main")
                status = "OK" if n_tgt >= n_src else "!! UBYTEK"
                if n_tgt < n_src:
                    ok = False
                print(f"  [{status}] {t:20} źródło={n_src:>7}  cel={n_tgt:>7}")
            conn.execute("DETACH DATABASE src")
        finally:
            conn.close()
    print()
    print("WYNIK:", "OK — migracja kompletna" if ok else "BŁĄD — ubytek wierszy!")
    print("Oryginały NIE zostały usunięte (rollback). Po weryfikacji można je zarchiwizować.")
    return ok


def main() -> int:
    ap = argparse.ArgumentParser(description="Migracja do baz per domena.")
    ap.add_argument(
        "--src-scouting",
        type=Path,
        default=_REPO_ROOT / "scouting.db",
        help="Źródłowy scouting.db (profiles + api_cache).",
    )
    ap.add_argument(
        "--src-drafts",
        type=Path,
        default=_APP_ROOT / "draft_analyzer" / "drafts.db",
        help="Źródłowy drafts.db (drafty + gracze + kohorta).",
    )
    args = ap.parse_args()
    return 0 if migrate(args.src_scouting, args.src_drafts) else 1


if __name__ == "__main__":
    raise SystemExit(main())
