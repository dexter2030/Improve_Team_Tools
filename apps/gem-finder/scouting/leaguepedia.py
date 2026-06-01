"""KROK 1 pipeline'u: lista aktywnych graczy z wybranych lig na Leaguepedii.

Wcześniej był tu osobny klient Cargo API (requests + paginacja); ta cała
warstwa została scalona ze wspólnym `src/api/leaguepedia_client.py` —
używają go też draft_analyzer, hidden_gems i app/main.py. Tutaj zostaje
TYLKO orkiestracja KROKU 1: turnamenty -> dedup po graczu -> meta z tabeli
Players -> wynikowy dict gotowy dla pipeline.py.
"""
from __future__ import annotations

import logging
from datetime import datetime

from shared.api.leaguepedia_client import LeaguepediaClient

LOG = logging.getLogger(__name__)


def fetch_all_players(
    leagues: list[str],
    active_since: datetime,
    roles: list[str] | None = None,
    user_agent: str = "gem-finder/0.1",
) -> list[dict]:
    """Pełna lista aktywnych graczy z wybranych lig.

    Pod spodem:
      1. TournamentPlayers JOIN Tournaments — najświeższy turniej dla
         każdego gracza, filtrowany lig­ą i datą startu.
      2. Players (meta) — kraj, residency, nick (ID), IsRetired.
      3. Połączenie i odsianie retired / niepasującej roli.

    Zwraca listę dictów: page_name, nick, team, role, country, residency,
    league, leaguepedia_url.
    """
    client = LeaguepediaClient(user_agent=user_agent)
    LOG.info(
        "Leaguepedia: tournament players for %s since %s",
        leagues, active_since.date(),
    )

    tp = client.get_tournament_players(
        leagues=leagues,
        active_since_date=active_since.strftime("%Y-%m-%d"),
    )
    LOG.info("Leaguepedia: %d unique tournament participants", len(tp))
    if not tp:
        return []

    meta = client.get_players_meta(list(tp.keys()))
    LOG.info("Leaguepedia: %d player meta rows", len(meta))

    out: list[dict] = []
    for page_name, t in tp.items():
        m = meta.get(page_name, {})
        if str(m.get("IsRetired") or "").strip() in ("Yes", "1", "true", "True"):
            continue
        role = t.get("Role") or m.get("Role")
        if roles and role not in roles:
            continue
        out.append(
            {
                "page_name": page_name,
                "nick": (m.get("ID") or "").strip() or page_name,
                "team": (t.get("Team") or m.get("Team") or "").strip() or None,
                "role": (role or "").strip() or None,
                "country": (m.get("Country") or "").strip() or None,
                "residency": (m.get("Residency") or "").strip() or None,
                "league": (t.get("League") or "").strip() or None,
                "leaguepedia_url": (
                    "https://lol.fandom.com/wiki/"
                    + page_name.replace(" ", "_")
                ),
            }
        )
    LOG.info("Leaguepedia: %d players after filtering", len(out))
    return out
