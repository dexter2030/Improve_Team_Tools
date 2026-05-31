"""
src/paths.py — centralne ścieżki baz danych aplikacji streamlit-dashboard.

Wszystkie pliki .db żyją w jednym katalogu danych (`data/`), a kod sięga po
nie przez te stałe zamiast hardcode'ować ścieżki względne. Katalog można
nadpisać zmienną środowiskową ``DASHBOARD_DATA_DIR`` (np. w deploy/CI).

Etapowanie:
- P2 (ten stan): topologia przejściowa — relokacja istniejących plików do
  ``data/`` bez podziału tabel (dwa pliki, jak dotąd).
- P3: podział na bazy per domena (profiles / cache / drafts / players /
  cohort) + migracja danych.
"""
from __future__ import annotations

import os
from pathlib import Path

DATA_DIR = Path(
    os.environ.get("DASHBOARD_DATA_DIR")
    or (Path(__file__).resolve().parents[1] / "data")
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Topologia przejściowa (P2): te same dwa pliki co wcześniej, tylko w data/.
SCOUTING_DB = DATA_DIR / "scouting.db"  # tabele: profiles + api_cache
DRAFTS_DB = DATA_DIR / "drafts.db"      # tabele: drafts + league_sync + players* + kohorta
