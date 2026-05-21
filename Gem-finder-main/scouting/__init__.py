"""Pipeline scoutingowy Gem-finder — Leaguepedia + Riot API + SQLite.

Klienci API (`src/api/leaguepedia_client.py`, `src/api/riot_client.py`) są
wspólni dla całego projektu, leżą piętro wyżej (`Sessions/src/`).
Dodajemy ten katalog do sys.path, żeby `Gem-finder-main` można było
uruchomić zarówno jako część głównego repo (cwd = Sessions/), jak i
samodzielnie (`python -m scouting.pipeline` z Gem-finder-main/).
"""
import sys
from pathlib import Path

_SESSIONS_ROOT = Path(__file__).resolve().parents[2]
if str(_SESSIONS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SESSIONS_ROOT))

from .pipeline import bootstrap, refresh_stale, add_manual_player, PipelineStats

__all__ = ["bootstrap", "refresh_stale", "add_manual_player", "PipelineStats"]
