import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Wczytaj .env z katalogu aplikacji (niezależnie od cwd, z którego odpalono).
load_dotenv(ROOT / ".env")


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    # Rozwiń ścieżkę bazy do absolutnej (względem katalogu aplikacji), z
    # możliwością nadpisania przez GEM_FINDER_DB. Dzięki temu pipeline pisze
    # zawsze do apps/gem-finder/data/gem_finder.db, niezależnie od cwd — i nie
    # koliduje z bazami aplikacji streamlit-dashboard.
    paths = cfg.setdefault("paths", {})
    db = os.environ.get("GEM_FINDER_DB") or paths.get("database", "data/gem_finder.db")
    db_path = Path(db)
    if not db_path.is_absolute():
        db_path = ROOT / db_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    paths["database"] = str(db_path)
    return cfg


def riot_api_key() -> str:
    key = os.getenv("RIOT_API_KEY")
    if not key:
        raise RuntimeError(
            "RIOT_API_KEY not set — kopiuj .env.example do .env i wpisz klucz z developer.riotgames.com"
        )
    return key
