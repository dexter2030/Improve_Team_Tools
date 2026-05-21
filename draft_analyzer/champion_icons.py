"""
champion_icons.py — adresy URL ikon championów z Riot Data Dragon.

Data Dragon to publiczne CDN Riot z grafikami gry. Ikony championów leżą pod
  https://ddragon.leagueoflegends.com/cdn/<wersja>/img/champion/<id>.png
gdzie <id> to wewnętrzny identyfikator championa (np. "MonkeyKing" dla
Wukonga). Mapę „nazwa wyświetlana -> id" budujemy raz z champion.json
i trzymamy w pamięci procesu (cache na czas życia aplikacji).

Brak sieci / nietrafiona nazwa => icon_url() zwraca None, a UI pokazuje
samą nazwę championa bez ikony.
"""

import requests

_VERSIONS_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
_CHAMPS_URL = ("https://ddragon.leagueoflegends.com/cdn/{ver}"
               "/data/en_US/champion.json")
_ICON_URL = ("https://ddragon.leagueoflegends.com/cdn/{ver}"
             "/img/champion/{cid}.png")

# Leniwie wypełniany cache na czas życia procesu (przeżywa rerun Streamlita).
_version: str | None = None
_name_to_id: dict[str, str] | None = None
_load_failed = False


def _key(name: str) -> str:
    """Normalizuje nazwę championa do porównań: małe litery, tylko alfanum.

    Dzięki temu „Xin Zhao", „Bel'Veth", „Nunu & Willump" itp. dopasują się
    niezależnie od spacji, apostrofów i wielkości liter.
    """
    return "".join(ch for ch in name.lower() if ch.isalnum())


def _load() -> None:
    """Pobiera wersję Data Dragon i mapę nazwa->id (jednorazowo na proces)."""
    global _version, _name_to_id, _load_failed
    if _name_to_id is not None or _load_failed:
        return
    try:
        versions = requests.get(_VERSIONS_URL, timeout=10).json()
        ver = versions[0]
        data = requests.get(
            _CHAMPS_URL.format(ver=ver), timeout=10
        ).json()["data"]
        _name_to_id = {_key(c["name"]): c["id"] for c in data.values()}
        _version = ver
    except Exception:
        # brak sieci / zmiana API — UI poradzi sobie bez ikon
        _load_failed = True


def icon_url(champion: str | None) -> str | None:
    """Zwraca URL ikony championa albo None.

    None oznacza: pusta nazwa, brak sieci przy pierwszym pobraniu danych
    Data Dragon, albo nazwa nie pasuje do żadnego championa (np. literówka).
    """
    if not champion or not champion.strip():
        return None
    _load()
    if _name_to_id is None:
        return None
    cid = _name_to_id.get(_key(champion))
    if cid is None:
        return None
    return _ICON_URL.format(ver=_version, cid=cid)
