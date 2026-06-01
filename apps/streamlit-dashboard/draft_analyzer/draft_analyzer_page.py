"""
draft_analyzer_page.py — zakładka Draft Analyzer dla aplikacji Streamlit.

Punkt wejścia modułu to funkcja render(). Aplikacja (app/main.py) wywołuje
ją w miejscu zakładki:

    from draft_analyzer.draft_analyzer_page import render
    render()

Logika obliczeniowa siedzi w analyzer.py (czyste funkcje) — ten plik
odpowiada wyłącznie za warstwę UI (Streamlit). Importy są pakietowe
(względne), więc moduł działa po wpięciu jako pakiet `draft_analyzer`.
"""

import pandas as pd
import streamlit as st

from .analyzer import (
    filter_by_leagues, first_pick_stats, phase1_ban_stats,
    search_drafts, suggest_all,
)
from .champion_icons import icon_url
from .db import clear_drafts_caches, fetch_all_drafts, init_db, list_patches
from .leagues import PRESETS, DEFAULT_PRESET, all_known_leagues
from .sync import fetch_league


def render():
    """Renderuje całą zakładkę. Wywołaj raz w miejscu zakładki."""
    init_db()  # tworzy tabelę przy pierwszym uruchomieniu

    st.title("🎯 Draft Analyzer")
    st.caption(
        "Pick & ban search over historical pro drafts + full draft database view."
    )

    # stan zakładki — przeżywa rerun Streamlita
    if "da_search" not in st.session_state:
        st.session_state.da_search = None
    if "da_leagues" not in st.session_state:
        st.session_state.da_leagues = list(PRESETS[DEFAULT_PRESET])
    if "da_patches" not in st.session_state:
        st.session_state.da_patches = []

    # ================= SEKCJA 1: pobieranie danych =================
    with st.expander("⚙️ Data — fetch drafts from Leaguepedia", expanded=False):
        st.write(
            "DB starts empty. Fetch once, then refresh periodically — fetch is "
            "incremental (only matches newer than the last cursor are pulled, "
            "so nothing is downloaded twice). League sync state and completeness "
            "% live in the **Database** tab."
        )
        col_a, col_b = st.columns([2, 1])
        league = col_a.text_input(
            "League", value="LEC",
            help="One league or several comma-separated — e.g., LEC, LPL, LCS",
        )
        season = col_a.text_input(
            "Season filter (optional)",
            value="",
            help="extra SQL-like condition, e.g., "
                 "ScoreboardGames.DateTime_UTC >= '2024-01-01'",
        )
        full_refresh = col_a.checkbox(
            "Full refresh (ignore stored cursor)",
            help="By default fetch only adds new matches. "
                 "Check to refetch the listed leagues from scratch.",
        )
        if col_b.button("Fetch", use_container_width=True):
            leagues_to_fetch = [s.strip() for s in league.split(",")
                                if s.strip()]
            if not leagues_to_fetch:
                st.warning("Provide at least one league.")
            else:
                _run_fetch(leagues_to_fetch, season, full_refresh)

    # ================= SEKCJA 2: wyszukiwarka draftów =================
    st.subheader("1 · Draft search")
    st.write(
        "Fill draft slots with champions — only the ones you care about. "
        "**Picks** match positionally: slot N on a side = the Nth pick of that team's "
        "draft. **Bans** go into a shared pool — side doesn't matter, but phase 1 "
        "(slots 1-3) and phase 2 (slots 4-5) are separated. For an empty pick slot, "
        "click 💡 — shows the most frequent champions at that exact position in "
        "matching drafts."
    )

    # Sugestie i wyniki wyszukiwania muszą działać na tym samym zbiorze,
    # żeby procenty w 💡 zgadzały się z proporcjami w tabeli wyników. Stąd
    # filtr patchy/lig liczymy najpierw — czytamy z session_state, bo
    # widżety renderują się niżej (Streamlit i tak rerunuje od góry, więc
    # po pierwszej interakcji wartości są dostępne).
    criteria = _criteria_from_state()
    filtered_drafts = filter_by_leagues(
        fetch_all_drafts(st.session_state.da_patches or None),
        st.session_state.da_leagues or None,
    )
    _, suggestions = suggest_all(filtered_drafts, criteria)

    _draft_grid(suggestions)

    # --- filtry zawężające: patch + ligi ---
    st.multiselect(
        "Patch filter (empty = all)",
        options=list_patches(),
        key="da_patches",
    )

    st.markdown("**League scope**")
    st.caption(
        "Presets are a quick start — you can still edit the list after clicking. "
        "Empty = all leagues in DB."
    )
    preset_cols = st.columns(len(PRESETS))
    for col, (name, leagues_preset) in zip(preset_cols, PRESETS.items()):
        if col.button(name, use_container_width=True, key=f"da_preset_{name}"):
            st.session_state.da_leagues = list(leagues_preset)
            st.rerun()
    st.multiselect(
        "Leagues in search",
        options=all_known_leagues(),
        key="da_leagues",
        help="Add or remove any leagues.",
    )

    if st.button("🔍 Search drafts", type="primary"):
        flat = (criteria["blue_picks"] + criteria["blue_bans"]
                + criteria["red_picks"] + criteria["red_bans"])
        if not any(flat):
            st.warning("Enter at least one champion.")
        else:
            st.session_state.da_search = {
                **criteria,
                "patches": st.session_state.da_patches or None,
                "leagues": st.session_state.da_leagues or None,
            }

    if st.session_state.da_search is not None:
        _render_search_results(st.session_state.da_search)

    # ================= SEKCJA 3: statystyki =================
    st.divider()
    _render_stats_section(filtered_drafts)

    # ================= SEKCJA 4: cała baza =================
    # Render za checkboxem — pełna baza to setki/tysiące wierszy i pełny
    # SELECT + budowa DataFrame'u. Renderowane domyślnie wymuszało ten koszt
    # na każdym rerunie (klik w patch też rerunuje całą stronę), nawet gdy
    # użytkownik patrzył tylko na wyszukiwarkę. Stan checkboxa żyje w
    # session_state — raz włączone zostaje, dopóki user nie wyłączy.
    st.divider()
    st.subheader("3 · Full draft database")
    show_all = st.checkbox(
        "Show full draft database",
        value=False,
        key="da_show_all_drafts",
        help="Loading the whole DB is slow for large datasets — click to expand.",
    )
    if show_all:
        all_drafts = fetch_all_drafts()
        if not all_drafts:
            st.info("DB is empty — fetch data from Leaguepedia above.")
        else:
            st.caption(
                f"{len(all_drafts)} drafts in DB · columns in draft order "
                f"(T1 = blue side, T2 = red side)."
            )
            _drafts_wide_table(all_drafts)


# --- helpery UI --------------------------------------------------------------

def _run_fetch(leagues: list[str], season: str, full_refresh: bool) -> None:
    """Pobiera drafty wybranych lig przyrostowo i pokazuje podsumowanie.

    Pobieranie dokłada tylko mecze nowsze niż ostatnio wczytane (kursor
    w tabeli league_sync) — `full_refresh` ignoruje kursor. Każda porcja
    trafia do bazy od razu, a upsert jest idempotentny, więc przerwane
    pobranie można bezpiecznie ponowić. Całość orkiestruje
    sync.fetch_league() — tu jest tylko pasek postępu i komunikaty.
    """
    n = len(leagues)
    bar = st.progress(0.0, text="Connecting to Leaguepedia…")
    outcomes = []
    for i, lg in enumerate(leagues):
        bar.progress(i / n, text=f"Fetching {lg}… ({i + 1}/{n})")

        def on_batch(fetched: int, saved: int, _lg=lg, _i=i) -> None:
            bar.progress(_i / n, text=f"{_lg}: saved {saved} games")

        outcomes.append(
            fetch_league(lg, season_where=season,
                         full_refresh=full_refresh, on_batch=on_batch)
        )
    bar.progress(1.0, text="Done.")

    # Wpadły nowe drafty (lub byłe upserty zmieniły patche/teams) — cache
    # SELECT-ów dla wyszukiwarki i list filtrów jest nieaktualny.
    clear_drafts_caches()

    saved = sum(o.saved for o in outcomes)
    errors = [o for o in outcomes if o.error]
    if errors:
        st.warning(f"Saved {saved} new games, but some leagues errored.")
    else:
        st.success(
            f"Fetched {n} leagues — saved {saved} new games "
            f"({', '.join(leagues)})."
        )

    for o in outcomes:
        if o.error:
            st.error(
                f"⚠️ {o.league}: fetch failed — {o.error}. "
                f"Already-saved games stay in DB; wait a minute and retry "
                f"(idempotent — only missing games will be added)."
            )
        elif o.truncated:
            st.warning(
                f"⚠️ {o.league}: hit limit of {o.fetched} rows. "
                f"Narrow by season filter to fetch older matches."
            )


# Wiersze siatki w kolejności draftu (jak na zdjęciu): bany 1-3, picki 1-3,
# bany 4-5, picki 4-5. Krotka: (etykieta, czy_pick, klucz_blue, klucz_red).
_DRAFT_ROWS = [
    ("Ban", False, "da_bb0", "da_rb0"),
    ("Ban", False, "da_bb1", "da_rb1"),
    ("Ban", False, "da_bb2", "da_rb2"),
    ("Pick", True, "da_bp0", "da_rp0"),
    ("Pick", True, "da_bp1", "da_rp1"),
    ("Pick", True, "da_bp2", "da_rp2"),
    ("Ban", False, "da_bb3", "da_rb3"),
    ("Ban", False, "da_bb4", "da_rb4"),
    ("Pick", True, "da_bp3", "da_rp3"),
    ("Pick", True, "da_bp4", "da_rp4"),
]


def _criteria_from_state() -> dict:
    """Buduje wzorzec pick&ban z aktualnego stanu slotów siatki."""
    def slot(key: str) -> str:
        return (st.session_state.get(key) or "").strip()

    return {
        "blue_picks": [slot(f"da_bp{i}") for i in range(5)],
        "blue_bans": [slot(f"da_bb{i}") for i in range(5)],
        "red_picks": [slot(f"da_rp{i}") for i in range(5)],
        "red_bans": [slot(f"da_rb{i}") for i in range(5)],
    }


def _suggestion_key(slot_key: str) -> str:
    """
    Mapuje klucz slotu UI (np. 'da_bp2', 'da_rb4') na klucz grupy sugestii
    z analyzer._GROUPS. Picki -> per-pozycja, bany -> per-faza.
    """
    body = slot_key[len("da_"):]      # 'bp2', 'rb4', ...
    kind, idx = body[:2], int(body[2:])
    if kind == "bp":
        return f"bp{idx}"
    if kind == "rp":
        return f"rp{idx}"
    if kind in ("bb", "rb"):
        return "phase1_bans" if idx < 3 else "phase2_bans"
    return ""


def _draft_grid(suggestions: dict) -> None:
    """Renderuje siatkę draftu — wiersze w kolejności jak na zdjęciu.

    Każdy wiersz to krok draftu: slot Blue, etykieta (Ban/Pick), slot Red.
    Przy wypełnionym slocie pokazuje ikonę championa; przy pustym slocie
    pick — przycisk 💡 otwierający popover z sugestiami dla tej dokładnie
    pozycji (bo picki dopasowywane są pozycyjnie).
    """
    for label, is_pick, b_key, r_key in _DRAFT_ROWS:
        c_bx, c_bi, c_lbl, c_ri, c_rx = st.columns(
            [2, 5, 2, 5, 2], vertical_alignment="center"
        )
        c_bi.text_input(b_key, key=b_key, placeholder="champion",
                        label_visibility="collapsed")
        c_ri.text_input(r_key, key=r_key, placeholder="champion",
                        label_visibility="collapsed")
        with c_bx:
            _slot_extra(b_key, is_pick,
                        suggestions.get(_suggestion_key(b_key), []))
        c_lbl.markdown(
            f"<div style='text-align:center; color:#888;'>{label}</div>",
            unsafe_allow_html=True,
        )
        with c_rx:
            _slot_extra(r_key, is_pick,
                        suggestions.get(_suggestion_key(r_key), []))


def _slot_extra(slot_key: str, is_pick: bool, group_suggestions: list) -> None:
    """Dodatek przy slocie: ikona championa (gdy wpisany) albo popover
    z sugestiami (gdy pusty slot typu pick)."""
    current = (st.session_state.get(slot_key) or "").strip()
    if current:
        url = icon_url(current)
        if url:
            st.image(url, width=44)
    elif is_pick:
        with st.popover("💡", use_container_width=True):
            _render_suggestions(group_suggestions)


def _render_suggestions(suggestions: list) -> None:
    """Treść popovera: sugerowane championy dla tego slotu + pick rate %."""
    st.markdown("**Most common in this situation**")
    if not suggestions:
        st.caption(
            "Fill in other slots — suggestions are computed from drafts "
            "matching the pattern."
        )
        return
    for s in suggestions[:6]:
        caption = f"{s['champion']} · {s['pct']}%  ({s['count']})"
        url = icon_url(s["champion"])
        if url:
            st.image(url, width=40, caption=caption)
        else:
            st.write(caption)


def _render_stats_section(drafts: list[dict]) -> None:
    """Sekcja statystyk: top bany fazy 1 per strona + top first picki.

    Liczone na tych samych draftach co sugestie i wyszukiwarka (filtry
    patchy + lig), żeby coach widział meta dla zawężonego regionu /
    okna patchowego. Bez wzorca pick&ban — to po prostu top-listy.
    """
    st.subheader("2 · Stats")
    st.caption(
        f"Most common phase 1 bans (per side) and first picks — from drafts "
        f"matching the current patch + league filter ({len(drafts)} drafts). "
        f"Change filters above to narrow to a specific meta or region."
    )
    if not drafts:
        st.info("No drafts in the current filter range.")
        return

    ban_stats = phase1_ban_stats(drafts, top_n=10)
    col_blue, col_red = st.columns(2)
    with col_blue:
        st.markdown("**Phase 1 bans — Blue side** (slots 1-3)")
        _render_champion_list(ban_stats["blue"])
    with col_red:
        st.markdown("**Phase 1 bans — Red side** (slots 1-3)")
        _render_champion_list(ban_stats["red"])

    st.markdown("**Top first picks** (first pick of the draft, Blue side)")
    _render_champion_list(first_pick_stats(drafts, top_n=10))


def _render_champion_list(stats: list[dict]) -> None:
    """Lista championów: ikonka + nazwa + % i liczba draftów."""
    if not stats:
        st.caption("No data.")
        return
    for s in stats:
        c_icon, c_name, c_pct = st.columns(
            [1, 4, 3], vertical_alignment="center"
        )
        url = icon_url(s["champion"])
        if url:
            c_icon.image(url, width=32)
        c_name.markdown(f"**{s['champion']}**")
        c_pct.caption(f"{s['pct']}% · {s['count']} drafts")


def _render_search_results(search: dict) -> None:
    """Filtruje bazę wg wzorca pick&ban i renderuje wynik wyszukiwania."""
    drafts = fetch_all_drafts(search["patches"])
    if not drafts:
        st.info("DB is empty — fetch data from Leaguepedia above.")
        return

    drafts = filter_by_leagues(drafts, search["leagues"])
    matches = search_drafts(
        drafts,
        blue_picks=search["blue_picks"],
        blue_bans=search["blue_bans"],
        red_picks=search["red_picks"],
        red_bans=search["red_bans"],
    )

    st.markdown(f"**Matches found: {len(matches)}**")
    if not matches:
        st.info(
            "No drafts match this pattern. Try fewer criteria or widen the "
            "league / patch filter."
        )
    elif len(matches) == 1:
        _draft_card(matches[0])
    else:
        _drafts_wide_table(matches)


def _draft_card(d: dict) -> None:
    """Jeden draft w układzie z obrazka 1 — wiersze draftu z ikonami."""
    blue = d.get("blue_team") or "Blue"
    red = d.get("red_team") or "Red"
    st.markdown(f"### {blue}  vs  {red}")
    meta = " · ".join(x for x in [
        d.get("league"),
        f"patch {d['patch']}" if d.get("patch") else None,
        f"date {d['game_date']}" if d.get("game_date") else None,
        f"winner: {d['winner']}" if d.get("winner") else None,
    ] if x)
    if meta:
        st.caption(meta)

    bb = list(d.get("blue_bans") or []) + [""] * 5
    rb = list(d.get("red_bans") or []) + [""] * 5
    # kolejność jak na obrazku 1: bany 1-3, picki 1-3, bany 4-5, picki 4-5
    steps = [
        ("Ban", bb[0], rb[0]),
        ("Ban", bb[1], rb[1]),
        ("Ban", bb[2], rb[2]),
        ("Pick", d.get("b1_pick"), d.get("r1_pick")),
        ("Pick", d.get("b2_pick"), d.get("r2_pick")),
        ("Pick", d.get("b3_pick"), d.get("r3_pick")),
        ("Ban", bb[3], rb[3]),
        ("Ban", bb[4], rb[4]),
        ("Pick", d.get("b4_pick"), d.get("r4_pick")),
        ("Pick", d.get("b5_pick"), d.get("r5_pick")),
    ]
    for faza, b, r in steps:
        c_bx, c_bn, c_l, c_rn, c_rx = st.columns(
            [1, 5, 2, 5, 1], vertical_alignment="center"
        )
        _card_cell(c_bx, c_bn, b)
        c_l.markdown(
            f"<div style='text-align:center; color:#888;'>{faza}</div>",
            unsafe_allow_html=True,
        )
        _card_cell(c_rx, c_rn, r)


def _card_cell(icon_col, name_col, champ: str | None) -> None:
    """Komórka karty draftu: ikona championa + nazwa (puste -> kreska)."""
    champ = (champ or "").strip()
    if not champ:
        name_col.markdown("—")
        return
    url = icon_url(champ)
    if url:
        icon_col.image(url, width=32)
    name_col.markdown(champ)


def _draft_row(d: dict) -> dict:
    """Jeden draft jako wiersz szerokiej tabeli (kolumny w kolejności draftu)."""
    bb = list(d.get("blue_bans") or []) + [""] * 5
    rb = list(d.get("red_bans") or []) + [""] * 5

    def pk(key: str) -> str:
        return d.get(key) or ""

    return {
        "Blue": d.get("blue_team") or "",
        "Red": d.get("red_team") or "",
        "Winner": d.get("winner") or "",
        "Patch": d.get("patch") or "",
        "T1B1": bb[0], "T2B1": rb[0], "T1B2": bb[1], "T2B2": rb[1],
        "T1B3": bb[2], "T2B3": rb[2],
        "T1P1": pk("b1_pick"), "T2P1": pk("r1_pick"), "T2P2": pk("r2_pick"),
        "T1P2": pk("b2_pick"), "T1P3": pk("b3_pick"), "T2P3": pk("r3_pick"),
        "T1B4": bb[3], "T2B4": rb[3], "T1B5": bb[4], "T2B5": rb[4],
        "T2P4": pk("r4_pick"), "T1P4": pk("b4_pick"),
        "T1P5": pk("b5_pick"), "T2P5": pk("r5_pick"),
    }


def _drafts_wide_table(drafts: list[dict]) -> None:
    """Drafty w szerokiej tabeli z obrazka 2 (kolumny w kolejności draftu)."""
    df = pd.DataFrame([_draft_row(d) for d in drafts])
    st.dataframe(df, use_container_width=True, hide_index=True)
