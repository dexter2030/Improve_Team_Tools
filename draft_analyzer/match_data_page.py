"""
match_data_page.py — zakładka „Match Data": wszystkie wczytane drafty.

Wyświetla całą bazę draftów (pełna sekwencja pick&ban) w szerokiej tabeli
z kolumnami w kolejności draftu (T1 = blue side, T2 = red side). Filtry
po lidze, patchu i drużynie pozwalają zawęzić widok bez wchodzenia w
Draft Analyzer.

Pobieranie nowych draftów nadal odbywa się w zakładce **Database** —
ta zakładka jest tylko widokiem na to, co już jest w bazie.

Punkt wejścia to render() — app/main.py wywołuje ją w miejscu zakładki.
"""

import pandas as pd
import streamlit as st

from .analyzer import filter_by_leagues
from .db import (
    count_all_drafts,
    fetch_all_drafts,
    init_db,
    list_patches,
    list_teams,
)
from .leagues import PRESETS, all_known_leagues


def render():
    """Renderuje zakładkę Match Data. Wywołać raz w miejscu zakładki."""
    init_db()  # tworzy tabele przy pierwszym uruchomieniu

    st.title("🗂️ Match Data")
    st.caption(
        "Wszystkie wczytane drafty z bazy — pełna sekwencja pick&ban. "
        "Pobieranie nowych meczów: zakładka **Database**."
    )

    total = count_all_drafts()
    if total == 0:
        st.info(
            'Baza draftów jest pusta. Wczytaj ligi w zakładce **Database** '
            'albo w sekcji „Dane" zakładki **Draft Analyzer**.'
        )
        return

    # --- filtry ---
    f1, f2 = st.columns(2)
    with f1:
        patches = st.multiselect(
            "Filtr patchy (puste = wszystkie)",
            options=list_patches(),
            key="md_patches",
        )
    with f2:
        teams = st.multiselect(
            "Filtr drużyn (puste = wszystkie)",
            options=list_teams(),
            key="md_teams",
            help="Dopasowanie po stronie blue LUB red.",
        )

    st.markdown("**Zakres lig**")
    st.caption(
        "Presety to szybki start — po kliknięciu listę nadal można edytować. "
        "Puste = wszystkie ligi w bazie."
    )
    preset_cols = st.columns(len(PRESETS))
    for col, (name, leagues_preset) in zip(preset_cols, PRESETS.items()):
        if col.button(name, use_container_width=True,
                      key=f"md_preset_{name}"):
            st.session_state["md_leagues"] = list(leagues_preset)
            st.rerun()
    st.multiselect(
        "Ligi", options=all_known_leagues(), key="md_leagues",
        help="Dodaj lub usuń dowolne ligi.",
    )

    # --- pobranie + filtrowanie ---
    drafts = fetch_all_drafts(patches or None)
    drafts = filter_by_leagues(drafts, st.session_state.get("md_leagues") or None)
    if teams:
        team_set = set(teams)
        drafts = [
            d for d in drafts
            if (d.get("blue_team") in team_set
                or d.get("red_team") in team_set)
        ]

    st.caption(
        f"{len(drafts)} draftów po filtrach (z {total} w bazie). "
        f"Kolumny w kolejności draftu (T1 = blue side, T2 = red side)."
    )
    if not drafts:
        st.warning("Brak draftów pasujących do filtrów.")
        return

    st.dataframe(
        pd.DataFrame([_draft_row(d) for d in drafts]),
        use_container_width=True,
        hide_index=True,
    )


def _draft_row(d: dict) -> dict:
    """Jeden draft jako wiersz szerokiej tabeli (kolumny w kolejności draftu).

    Identyczny układ jak `draft_analyzer_page._draft_row`, powtórzony tu,
    żeby zakładka była samodzielna (nie ciągnęła UI sąsiedniej zakładki).
    """
    bb = list(d.get("blue_bans") or []) + [""] * 5
    rb = list(d.get("red_bans") or []) + [""] * 5

    def pk(key: str) -> str:
        return d.get(key) or ""

    return {
        "Liga":    d.get("league") or "",
        "Patch":   d.get("patch") or "",
        "Data":    d.get("game_date") or "",
        "Blue":    d.get("blue_team") or "",
        "Red":     d.get("red_team") or "",
        "Winner":  d.get("winner") or "",
        "T1B1": bb[0], "T2B1": rb[0], "T1B2": bb[1], "T2B2": rb[1],
        "T1B3": bb[2], "T2B3": rb[2],
        "T1P1": pk("b1_pick"), "T2P1": pk("r1_pick"), "T2P2": pk("r2_pick"),
        "T1P2": pk("b2_pick"), "T1P3": pk("b3_pick"), "T2P3": pk("r3_pick"),
        "T1B4": bb[3], "T2B4": rb[3], "T1B5": bb[4], "T2B5": rb[4],
        "T2P4": pk("r4_pick"), "T1P4": pk("b4_pick"),
        "T1P5": pk("b5_pick"), "T2P5": pk("r5_pick"),
    }
