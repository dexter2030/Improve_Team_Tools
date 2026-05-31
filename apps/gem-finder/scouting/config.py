import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else ROOT / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def riot_api_key() -> str:
    key = os.getenv("RIOT_API_KEY")
    if not key:
        raise RuntimeError(
            "RIOT_API_KEY not set — kopiuj .env.example do .env i wpisz klucz z developer.riotgames.com"
        )
    return key
