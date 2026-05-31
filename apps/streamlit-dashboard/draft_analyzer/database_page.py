"""
database_page.py — zakładka „Database": stan lokalnej bazy draftów.

Dla każdej ligi (Tier 1, ERL akredytowane = „ERL 1", ERL nieakredytowane
= „ERL 2") pokazuje:
  * ile draftów jest w lokalnej bazie,
  * jaki to procent tego, co udostępnia Leaguepedia (% kompletności),
  * kiedy liga była ostatnio wczytywana.

Każdą ligę można wczytać/odświeżyć wprost z tej zakładki. Pobieranie jest
przyrostowe — dokłada tylko mecze nowsze niż ostatnio pobrane, więc tego
samego meczu nie ściąga się dwa razy (mechanizm: sync.py).

Punkt wejścia to render() — app/main.py wywołuje ją w miejscu zakładki.
"""

import streamlit as st

from .db import (
    all_league_sync,
    clear_drafts_caches,
    count_all_drafts,
    count_drafts_for_league,
    init_db,
)
from .leaguepedia import auth_status
from .leagues import LEAGUE_GROUPS
from .sync import FetchOutcome, fetch_league

# Wagi kolumn wiersza ligi — wspólne dla nagłówka i wierszy danych.
_COLS = [3, 2, 5, 3, 2]


def render():
    """Renderuje całą zakładkę Database. Wywołać raz w miejscu zakładki."""
    init_db()  # tworzy tabele przy pierwszym uruchomieniu

    st.title("🗄️ Database")
    st.caption(
        "Local draft database state — when each league was synced and how "
        "complete it is vs. Leaguepedia. Incremental fetch: the same match "
        "is never fetched twice."
    )

    # Tryb dostępu do Leaguepedia — bot-password podnosi limit zapytań.
    auth_level, auth_msg = auth_status()
    {"ok": st.caption, "info": st.info, "warn": st.warning}[auth_level](auth_msg)

    # Komunikat z poprzedniej akcji — przeżywa st.rerun() w session_state.
    msg = st.session_state.pop("db_msg", None)
    if msg is not None:
        {"ok": st.success, "warn": st.warning, "err": st.error}[msg[0]](msg[1])

    sync = all_league_sync()
    all_leagues = [lg for group in LEAGUE_GROUPS.values() for lg in group]
    n_loaded = sum(
        1 for lg in all_leagues if sync.get(lg, {}).get("last_fetched")
    )

    m1, m2 = st.columns(2)
    m1.metric("Drafts in DB", count_all_drafts())
    m2.metric("Leagues synced", f"{n_loaded} / {len(all_leagues)}")

    full_refresh = st.checkbox(
        "Full refresh (ignore incremental cursor)",
        help="By default fetch only adds matches newer than the last sync. "
             "Check to refetch the league from scratch.",
    )
    if st.button("⬇️ Fetch all leagues", use_container_width=True):
        _fetch_and_report(all_leagues, full_refresh)

    st.divider()

    for label, leagues in LEAGUE_GROUPS.items():
        st.subheader(label)
        _league_rows(leagues, sync, full_refresh)
        st.write("")


# --- helpery UI --------------------------------------------------------------

def _league_rows(leagues: list[str], sync: dict, full_refresh: bool) -> None:
    """Renderuje nagłówek i po jednym wierszu na ligę z przyciskiem wczytania."""
    header = st.columns(_COLS, vertical_alignment="center")
    for col, title in zip(
        header, ["League", "In DB", "Completeness", "Last sync", ""]
    ):
        col.caption(title)

    for lg in leagues:
        row = sync.get(lg, {})
        local = count_drafts_for_league(lg)
        remote = row.get("remote_total")
        last_fetched = row.get("last_fetched")

        c_name, c_local, c_pct, c_last, c_btn = st.columns(
            _COLS, vertical_alignment="center"
        )
        c_name.markdown(f"**{lg}**")
        c_local.write(str(local))

        if remote:
            # Lokalnie zapisujemy tylko drafty z pełnym pick&ban, więc
            # przy drobnych rozbieżnościach licznika tniemy do 100%.
            pct = min(local / remote, 1.0)
            c_pct.progress(pct, text=f"{pct:.0%} ({local}/{remote})")
        elif remote == 0:
            c_pct.caption("no drafts on Leaguepedia")
        else:
            c_pct.caption("— fetch to count")

        c_last.write(_fmt_dt(last_fetched) if last_fetched else "—")

        label = "↻ Refresh" if last_fetched else "⬇️ Fetch"
        if c_btn.button(label, key=f"db_load_{lg}",
                        use_container_width=True):
            _fetch_and_report([lg], full_refresh)


def _fmt_dt(iso: str) -> str:
    """Skraca znacznik ISO ('2026-05-18T14:30:00') do 'YYYY-MM-DD HH:MM'."""
    return iso.replace("T", " ")[:16]


def _fetch_and_report(leagues: list[str], full_refresh: bool) -> None:
    """Wczytuje podane ligi z paskiem postępu, zapisuje komunikat, przeładowuje.

    Wynik trafia do session_state (przeżyje st.rerun) i jest pokazany na
    górze zakładki po przeładowaniu — wtedy tabela ma już świeże dane.
    """
    n = len(leagues)
    bar = st.progress(0.0, text="Connecting to Leaguepedia…")
    outcomes: list[FetchOutcome] = []
    for i, lg in enumerate(leagues):
        bar.progress(i / n, text=f"Fetching {lg}… ({i + 1}/{n})")

        def on_batch(fetched: int, saved: int, _lg=lg, _i=i) -> None:
            bar.progress(
                _i / n, text=f"{_lg}: fetched {fetched}, saved {saved}"
            )

        outcomes.append(
            fetch_league(lg, full_refresh=full_refresh, on_batch=on_batch)
        )
    bar.progress(1.0, text="Done.")

    # Świeże drafty + zaktualizowane liczniki league_sync — unieważniamy
    # cache odczytów, żeby render po st.rerun() pokazał aktualne dane.
    clear_drafts_caches()

    st.session_state["db_msg"] = _summary(outcomes)
    st.rerun()


def _summary(outcomes: list[FetchOutcome]) -> tuple[str, str]:
    """Buduje (poziom, treść) komunikatu po wczytaniu — poziom: ok/warn/err."""
    saved = sum(o.saved for o in outcomes)
    errors = [o for o in outcomes if o.error]
    truncated = [o for o in outcomes if o.truncated and not o.error]

    lines = [
        f"Synced {len(outcomes)} leagues · saved {saved} new drafts."
    ]
    for o in errors:
        lines.append(
            f"❌ **{o.league}** — fetch failed: {o.error}. "
            f"Already-saved drafts stay; retry the sync (idempotent — "
            f"only missing drafts will be added)."
        )
    for o in truncated:
        lines.append(
            f"⚠️ **{o.league}** — hit limit of {o.fetched} rows. "
            f"Older matches may not have been fetched; narrow by season "
            f"filter in the Draft Analyzer tab."
        )
    level = "err" if errors else ("warn" if truncated else "ok")
    return level, "\n\n".join(lines)
