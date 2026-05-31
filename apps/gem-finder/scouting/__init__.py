"""Pipeline scoutingowy Gem-finder — Leaguepedia + Riot API + SQLite.

Klienci API (`shared.api.leaguepedia_client`, `shared.api.riot_client`) są
wspólni dla całego monorepo i leżą w `packages/shared/`. Dokładamy ten
katalog do sys.path, żeby `import shared.*` działał niezależnie od cwd —
zarówno jako część repo, jak i samodzielnie (`python -m scouting.pipeline`
z `apps/gem-finder/`).
"""
import sys
from pathlib import Path

_shared = next(
    a for a in Path(__file__).resolve().parents if (a / "packages" / "shared").is_dir()
) / "packages" / "shared"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))

from .pipeline import bootstrap, refresh_stale, add_manual_player, PipelineStats

__all__ = ["bootstrap", "refresh_stale", "add_manual_player", "PipelineStats"]
