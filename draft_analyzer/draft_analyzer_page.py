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
from .db import init_db, fetch_all_drafts, list_patches
from .leagues import PRESETS, DEFAULT_PRESET, all_known_leagues
from .sync import fetch_league


def render():
    """Renderuje całą zakładkę. Wywołaj raz w miejscu zakładki."""
    init_db()  # tworzy tabelę przy pierwszym uruchomieniu

    st.title("🎯 Draft Analyzer")
    st.caption(
        "Wyszukiwarka historycznych draftów po wzorcu pick&ban "
        "oraz podgląd całej bazy draftów."
    )

    # stan zakładki — przeżywa rerun Streamlita
    if "da_search" not in st.session_state:
        st.session_state.da_search = None
    if "da_leagues" not in st.session_state:
        st.session_state.da_leagues = list(PRESETS[DEFAULT_PRESET])
    if "da_patches" not in st.session_state:
        st.session_state.da_patches = []

    # ================= SEKCJA 1: pobieranie danych =================
    with st.expander("⚙️ Dane — pobierz drafty z Leaguepedia", expanded=False):
        st.write(
            "Baza startuje pusta. Pobierz drafty raz, potem odświeżaj "
            "okresowo — pobieranie jest przyrostowe (dokłada tylko mecze "
            "nowsze niż ostatnio wczytane, więc tego samego nie ściąga "
            "się dwa razy). Stan i % kompletności każdej ligi widać "
            "w zakładce **Database**."
        )
        col_a, col_b = st.columns([2, 1])
        league = col_a.text_input(
            "Liga", value="LEC",
            help="Jedna liga lub kilka po przecinku — np. LEC, LPL, LCS",
        )
        season = col_a.text_input(
            "Filtr sezonu (opcjonalnie)",
            value="",
            help="dodatkowy warunek SQL, np. "
                 "ScoreboardGames.DateTime_UTC >= '2024-01-01'",
        )
        full_refresh = col_a.checkbox(
            "Pełne odświeżenie (ignoruj zapamiętany postęp)",
            help="Domyślnie pobieranie dokłada tylko nowe mecze. "
                 "Zaznacz, by pobrać wskazane ligi całe od nowa.",
        )
        if col_b.button("Pobierz dane", use_container_width=True):
            leagues_to_fetch = [s.strip() for s in league.split(",")
                                if s.strip()]
            if not leagues_to_fetch:
                st.warning("Podaj przynajmniej jedną ligę.")
            else:
                _run_fetch(leagues_to_fetch, season, full_refresh)

    # ================= SEKCJA 2: wyszukiwarka draftów =================
    st.subheader("1 · Wyszukiwarka draftów")
    st.write(
        "Wpisz championów w sloty draftu — wypełnij tylko te, na których Ci "
        "zależy. **Picki** dopasowywane są pozycyjnie: slot N po danej "
        "stronie = N-ty pick draftu tej drużyny. **Bany** trafiają do "
        "wspólnej puli — strona nie ma znaczenia, ale faza 1 (sloty 1-3) "
        "i faza 2 (sloty 4-5) są rozdzielone. Przy pustym slocie pick "
        "kliknij 💡 — pokaże najczęstsze championy na tej dokładnie "
        "pozycji w pasujących draftach."
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
        "Filtr patchy (puste = wszystkie)",
        options=list_patches(),
        key="da_patches",
    )

    st.markdown("**Zakres lig**")
    st.caption(
        "Presety to szybki start — po kliknięciu listę nadal można "
        "dowolnie edytować. Puste = wszystkie ligi w bazie."
    )
    preset_cols = st.columns(len(PRESETS))
    for col, (name, leagues_preset) in zip(preset_cols, PRESETS.items()):
        if col.button(name, use_container_width=True, key=f"da_preset_{name}"):
            st.session_state.da_leagues = list(leagues_preset)
            st.rerun()
    st.multiselect(
        "Ligi w wyszukiwaniu",
        options=all_known_leagues(),
        key="da_leagues",
        help="Dodaj lub usuń dowolne ligi.",
    )

    if st.button("🔍 Szukaj draftów", type="primary"):
        flat = (criteria["blue_picks"] + criteria["blue_bans"]
                + criteria["red_picks"] + criteria["red_bans"])
        if not any(flat):
            st.warning("Wpisz przynajmniej jednego championa.")
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
    st.divider()
    st.subheader("3 · Cała baza draftów")
    all_drafts = fetch_all_drafts()
    if not all_drafts:
        st.info("Baza jest pusta — pobierz dane z Leaguepedia powyżej.")
    else:
        st.caption(
            f"{len(all_drafts)} draftów w bazie · kolumny w kolejności "
            f"draftu (T1 = blue side, T2 = red side)."
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
    bar = st.progress(0.0, text="Łączę się z Leaguepedia…")
    outcomes = []
    for i, lg in enumerate(leagues):
        bar.progress(i / n, text=f"Wczytuję {lg}… ({i + 1}/{n})")

        def on_batch(fetched: int, saved: int, _lg=lg, _i=i) -> None:
            bar.progress(_i / n, text=f"{_lg}: zapisano {saved} gier")

        outcomes.append(
            fetch_league(lg, season_where=season,
                         full_refresh=full_refresh, on_batch=on_batch)
        )
    bar.progress(1.0, text="Gotowe.")

    saved = sum(o.saved for o in outcomes)
    errors = [o for o in outcomes if o.error]
    if errors:
        st.warning(f"Zapisano {saved} nowych gier, ale część lig zwróciła błąd.")
    else:
        st.success(
            f"Pobrano dane z {n} lig — zapisano {saved} nowych gier "
            f"({', '.join(leagues)})."
        )

    for o in outcomes:
        if o.error:
            st.error(
                f"⚠️ {o.league}: pobieranie przerwał błąd — {o.error}. "
                f"Już zapisane gry zostają w bazie; odczekaj minutę "
                f"i ponów pobieranie (jest idempotentne — dołoży tylko "
                f"brakujące gry)."
            )
        elif o.truncated:
            st.warning(
                f"⚠️ {o.league}: osiągnięto limit {o.fetched} wierszy. "
                f"Zawęź filtrem sezonu, by pobrać starsze mecze."
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
    st.markdown("**Najczęściej w tej sytuacji**")
    if not suggestions:
        st.caption(
            "Wpisz championów w inne sloty — sugestie liczone są z draftów "
            "pasujących do wzorca."
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
    st.subheader("2 · Statystyki")
    st.caption(
        f"Najczęstsze bany fazy 1 (per strona) oraz first picki — liczone "
        f"z draftów w aktualnym filtrze patchy + lig ({len(drafts)} "
        f"draftów). Zmień filtry powyżej, żeby zawęzić do interesującej "
        f"mety / regionu."
    )
    if not drafts:
        st.info("Brak draftów w wybranym zakresie filtrów.")
        return

    ban_stats = phase1_ban_stats(drafts, top_n=10)
    col_blue, col_red = st.columns(2)
    with col_blue:
        st.markdown("**Bany fazy 1 — Blue side** (sloty 1-3)")
        _render_champion_list(ban_stats["blue"])
    with col_red:
        st.markdown("**Bany fazy 1 — Red side** (sloty 1-3)")
        _render_champion_list(ban_stats["red"])

    st.markdown("**Najczęstsze first picki** (pierwszy pick draftu, Blue side)")
    _render_champion_list(first_pick_stats(drafts, top_n=10))


def _render_champion_list(stats: list[dict]) -> None:
    """Lista championów: ikonka + nazwa + % i liczba draftów."""
    if not stats:
        st.caption("Brak danych.")
        return
    for s in stats:
        c_icon, c_name, c_pct = st.columns(
            [1, 4, 3], vertical_alignment="center"
        )
        url = icon_url(s["champion"])
        if url:
            c_icon.image(url, width=32)
        c_name.markdown(f"**{s['champion']}**")
        c_pct.caption(f"{s['pct']}% · {s['count']} draftów")


def _render_search_results(search: dict) -> None:
    """Filtruje bazę wg wzorca pick&ban i renderuje wynik wyszukiwania."""
    drafts = fetch_all_drafts(search["patches"])
    if not drafts:
        st.info("Baza jest pusta — pobierz dane z Leaguepedia powyżej.")
        return

    drafts = filter_by_leagues(drafts, search["leagues"])
    matches = search_drafts(
        drafts,
        blue_picks=search["blue_picks"],
        blue_bans=search["blue_bans"],
        red_picks=search["red_picks"],
        red_bans=search["red_bans"],
    )

    st.markdown(f"**Znaleziono draftów: {len(matches)}**")
    if not matches:
        st.info(
            "Brak draftów pasujących do tego wzorca. Spróbuj mniej "
            "kryteriów albo poszerz filtr lig / patchy."
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
        f"data {d['game_date']}" if d.get("game_date") else None,
        f"zwycięzca: {d['winner']}" if d.get("winner") else None,
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
