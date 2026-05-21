"""
src/config.py — bootstrap sekretów dla aplikacji.

Aplikacja czyta klucze przez os.environ (Riot, Leaguepedia). Na Streamlit
Community Cloud nie ma .env — sekrety są wstrzykiwane do st.secrets przez
UI. Ten moduł godzi oba tryby:

  1. Lokalnie:        load_dotenv() wczytuje .env do os.environ.
  2. Streamlit Cloud: kopiuje wartości z st.secrets do os.environ.

Po wywołaniu bootstrap_secrets() reszta kodu (api/, processing/) może
spokojnie czytać os.environ.get(...) bez wiedzy o tym, skąd przyszły.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Klucze, które chcemy zaciągnąć do os.environ.
_SECRET_KEYS = (
    "RIOT_API_KEY",
    "LEAGUEPEDIA_USERNAME",
    "LEAGUEPEDIA_PASSWORD",
    "APP_PASSWORD",
)


def bootstrap_secrets() -> None:
    """Ładuje sekrety z .env (lokalnie) i st.secrets (Streamlit Cloud).

    Idempotentne — można wołać wielokrotnie. Wartość ustawiona w środowisku
    (np. eksport w shellu) ma pierwszeństwo i nie jest nadpisywana.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env")
    except Exception:
        pass

    try:
        import streamlit as st
        # st.secrets rzuca, jeśli plik secrets.toml nie istnieje i nie ma
        # sekretów wstrzykniętych przez Cloud. Cisza w tym wypadku.
        secrets = st.secrets
    except Exception:
        return

    for key in _SECRET_KEYS:
        if os.environ.get(key):
            continue
        try:
            value = secrets[key]
        except (KeyError, FileNotFoundError, Exception):
            continue
        if value:
            os.environ[key] = str(value)
