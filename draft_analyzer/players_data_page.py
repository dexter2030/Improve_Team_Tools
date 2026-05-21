"""
players_data_page.py — zakładka „Players Data": baza graczy z Leaguepedia.

Dwa tryby pobierania:
  1. **Globalnie (wszyscy gracze)** — pobiera całą tabelę `Players` z
     Leaguepedia, jeden wiersz na gracza, niezależnie od ligi. Filtruje
     się po narodowości i roli; dla każdego gracza można sprawdzić, czy
     ma profil na lolpros.gg.
  2. **Per liga** — pobiera roster turniejów z LEAGUE_GROUPS (Tier 1,
     ERL 1, ERL 2). Jeden gracz może mieć wiersz w wielu ligach.

Punkt wejścia to render() — app/main.py wywołuje ją w miejscu zakładki.
"""

import time

import pandas as pd
import streamlit as st

from .db import (
    all_players_sync,
    count_all_players_global,
    count_lolpros_unchecked,
    count_players_for_league,
    count_unique_players,
    fetch_all_players as fetch_per_league_players,
    fetch_all_players_global,
    get_all_players_global_sync,
    init_db,
    update_lolpros,
)
from .leaguepedia import auth_status
from .leagues import LEAGUE_GROUPS
from .lolpros import batch_check_lolpros
from .sync import (
    PlayersFetchOutcome,
    fetch_all_players as sync_fetch_all_players,
    fetch_players_for_league,
)

# Pauza między ligami w pobieraniu masowym (sekundy).
_INTER_LEAGUE_PAUSE = 1.5

# Pauza przed ponowieniem lig, które padły w pierwszym przebiegu (s).
_RETRY_COOLDOWN = 15.0

# Wagi kolumn wiersza ligi — wspólne dla nagłówka i wierszy danych.
_COLS = [3, 3, 4, 3]


def render():
    """Renderuje całą zakładkę Players Data. Wywołać raz w miejscu zakładki."""
    init_db()  # tworzy tabele przy pierwszym uruchomieniu

    st.title("👥 Players Data")
    st.caption(
        "Baza graczy z Leaguepedia. Dwa tryby: globalnie (cała tabela "
        "Players, bez podziału na ligi, z filtrami narodowość/rola i "
        "wskaźnikiem lolpros) oraz per liga (rostery turniejów)."
    )

    auth_level, auth_msg = auth_status()
    {"ok": st.caption, "info": st.info, "warn": st.warning}[auth_level](auth_msg)

    # Komunikaty po akcji — przeżywa st.rerun() w session_state.
    msg = st.session_state.pop("players_msg", None)
    if msg is not None:
        {"ok": st.success, "warn": st.warning, "err": st.error}[msg[0]](msg[1])
    lp_msg = st.session_state.pop("lolpros_msg", None)
    if lp_msg is not None:
        {"ok": st.success, "warn": st.warning, "err": st.error}[lp_msg[0]](lp_msg[1])

    # --- TRYB 1: wszyscy gracze, globalnie ---------------------------------
    _render_global_players_section()

    st.divider()

    # --- TRYB 2: per liga --------------------------------------------------
    _render_per_league_section()


# --- TRYB 1: globalna baza ---------------------------------------------------

def _render_global_players_section() -> None:
    """Sekcja „wszyscy gracze z Leaguepedia"  — bez podziału na ligi.

    Strukturalnie: nagłówek + status pobrania + przycisk pobierania,
    a poniżej tabela z filtrami (narodowość, rola) i kolumną lolpros.
    """
    st.header("🌍 Wszyscy gracze (globalnie)")
    st.caption(
        "Cała tabela `Players` z Leaguepedia — jeden wiersz na gracza, "
        "niezależnie od ligi. Filtruj po narodowości i roli. "
        "Kolumna lolpros pokazuje link do profilu lolpros.gg, jeśli "
        "gracz tam jest (sprawdzenie wymaga osobnego kliknięcia — "
        "lolpros to zewnętrzna strona, sprawdzenie idzie po HTTP)."
    )

    sync_row = get_all_players_global_sync()
    total = count_all_players_global()
    unchecked = count_lolpros_unchecked()

    m1, m2, m3 = st.columns(3)
    m1.metric("Graczy w bazie", total)
    m2.metric(
        "Ostatnie pobranie",
        _fmt_dt(sync_row["last_fetched"]) if sync_row else "—",
    )
    m3.metric("Bez sprawdzonego lolpros", unchecked)

    # Pobieranie — bez filtrów. Filtry na liście (poniżej) działają
    # po stronie klienta, więc raz pobrana baza obsłuży wszystkie.
    if st.button(
        "⬇️ Pobierz / odśwież globalną bazę graczy",
        use_container_width=True,
        help="Pobiera całą tabelę Players z Leaguepedia. To może potrwać "
             "minutę — Players ma ~30 tys. wierszy.",
    ):
        _fetch_all_and_report()

    if total == 0:
        st.info("Baza pusta — kliknij przycisk powyżej, by pobrać.")
        return

    # --- Tabela + filtry ---
    all_players = fetch_all_players_global()
    df = pd.DataFrame(all_players)
    df = df.rename(columns={
        "player_id":            "Nick",
        "overview_page":        "Leaguepedia",
        "role":                 "Rola",
        "team":                 "Drużyna",
        "country":              "Kraj",
        "residency":            "Rezydencja",
        "nationality_primary":  "Narodowość",
        "is_retired":           "Retired",
        "lolpros_url":          "Lolpros",
        "lolpros_checked_at":   "Lolpros sprawdzono",
        "last_fetched":         "Pobrane",
    })
    df["Retired"] = df["Retired"].map(
        lambda v: "tak" if str(v).strip() in ("1", "true", "True") else ""
    )

    f1, f2, f3 = st.columns(3)
    with f1:
        countries = sorted(c for c in df["Narodowość"].unique() if c)
        nat_filter = st.multiselect(
            "Narodowość", countries, default=[],
            help="Filtruje po Players.NationalityPrimary (kod kraju "
                 "w formie używanej przez Leaguepedia).",
        )
    with f2:
        roles_available = sorted(r for r in df["Rola"].unique() if r)
        role_filter = st.multiselect(
            "Rola", roles_available, default=[],
            help="Wartość z Players.Role na Leaguepedia.",
        )
    with f3:
        only_with_lolpros = st.checkbox(
            "Tylko z profilem lolpros",
            help="Pokaż tylko graczy, dla których sprawdzono lolpros i "
                 "znaleziono profil. Niezsprawdzeni są pomijani.",
        )
        hide_retired = st.checkbox(
            "Ukryj retired",
        )

    # Rozdzielenie filtrów: "data" (nat/rola/retired) decyduje, kogo w
    # ogóle bierzemy pod uwagę — także do sprawdzania lolpros. "Widok"
    # (tylko z lolprosem) zawęża tabelę, ale NIE wpływa na zakres
    # sprawdzania. Dzięki temu można włączyć „tylko z lolprosem" przed
    # pierwszym sprawdzeniem i nadal kliknąć sprawdź — sprawdzi tych,
    # którzy mają pasującą narodowość/rolę, niezsprawdzonych.
    data_filtered = df
    if nat_filter:
        data_filtered = data_filtered[data_filtered["Narodowość"].isin(nat_filter)]
    if role_filter:
        data_filtered = data_filtered[data_filtered["Rola"].isin(role_filter)]
    if hide_retired:
        data_filtered = data_filtered[data_filtered["Retired"] == ""]

    # Niezsprawdzeni w obrębie data_filtered — tylu czeka na pukanie.
    # Pusty „Lolpros sprawdzono" = NULL z DB = nigdy nie sprawdzano.
    unchecked = data_filtered[
        data_filtered["Lolpros sprawdzono"].isna()
        | (data_filtered["Lolpros sprawdzono"] == "")
    ]

    # Widok: opcjonalnie zawężony do tych z lolprosem.
    visible = data_filtered
    if only_with_lolpros:
        visible = visible[visible["Lolpros"].astype(bool)]

    st.caption(
        f"Widocznych: {len(visible)} · pasujących do filtrów: "
        f"{len(data_filtered)} · niezsprawdzonych: {len(unchecked)} "
        f"(baza: {len(df)})."
    )

    # Sprawdzanie idzie na wszystkich pasujących, nawet jeśli filtr
    # „tylko z lolprosem" ukrywa ich w tabeli. Pomijamy już sprawdzonych
    # — nie ma sensu pukać do lolprosa drugi raz.
    a1, a2 = st.columns([3, 1])
    a1.caption(
        "Sprawdzanie lolpros pomija już sprawdzonych — re-check możliwy "
        "po wyczyszczeniu kolumny `lolpros_checked_at` w bazie."
    )
    btn_label = (
        f"🔎 Sprawdź lolpros ({len(unchecked)} niezsprawdzonych)"
        if len(unchecked) > 0
        else "🔎 Wszyscy pasujący już sprawdzeni"
    )
    if a2.button(
        btn_label,
        use_container_width=True,
        disabled=len(unchecked) == 0,
    ):
        _check_lolpros_and_report(unchecked)

    # Tabela — Leaguepedia i Lolpros jako klikalne linki (LinkColumn).
    display_df = visible.copy()
    display_df["Leaguepedia"] = display_df["Leaguepedia"].map(
        lambda link: _leaguepedia_url(link) if link else ""
    )
    display_df["Lolpros sprawdzono"] = display_df["Lolpros sprawdzono"].map(
        lambda v: _fmt_dt(v) if v else "—"
    )

    display_cols = [
        "Nick", "Rola", "Drużyna", "Kraj", "Rezydencja", "Narodowość",
        "Retired", "Leaguepedia", "Lolpros", "Lolpros sprawdzono",
    ]
    display_df = display_df[display_cols]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Leaguepedia": st.column_config.LinkColumn(
                "Leaguepedia",
                display_text="otwórz",
            ),
            "Lolpros": st.column_config.LinkColumn(
                "Lolpros",
                display_text=r"https?://lolpros\.gg/player/(.*)",
            ),
        },
    )


def _leaguepedia_url(overview_page: str) -> str:
    """Składa URL strony wiki z nazwy OverviewPage."""
    return (
        "https://lol.fandom.com/wiki/"
        + overview_page.replace(" ", "_")
    )


def _fetch_all_and_report() -> None:
    """Pobiera globalną bazę graczy z paskiem postępu i komunikatem."""
    bar = st.progress(0.0, text="Łączę się z Leaguepedia…")

    # Players ma rzędu 30k wierszy. Pasek wyrażony w postępie do
    # tej liczby — niedokładny, ale daje feedback (Cargo nie zwraca
    # globalnego totalu, więc bierzemy przybliżenie).
    expected_total = 30000

    def on_progress(total_so_far: int) -> None:
        pct = min(total_so_far / expected_total, 0.95)
        bar.progress(pct, text=f"Pobrano {total_so_far} graczy…")

    outcome = sync_fetch_all_players(on_progress=on_progress)
    bar.progress(1.0, text="Gotowe.")

    if outcome.error:
        st.session_state["players_msg"] = (
            "err",
            f"Pobieranie globalnej bazy padło: {outcome.error}. "
            f"Już zapisane wiersze zostają w bazie.",
        )
    else:
        st.session_state["players_msg"] = (
            "ok",
            f"Pobrano {outcome.fetched} wierszy, zapisano "
            f"{outcome.saved} graczy do bazy globalnej.",
        )
    st.rerun()


def _check_lolpros_and_report(filtered_df: pd.DataFrame) -> None:
    """Sprawdza lolpros dla widocznych graczy, zapisuje wynik per wiersz.

    Sprawdzamy WSZYSTKICH widocznych — także już sprawdzonych — żeby
    UI był prosty (jedno kliknięcie = świeże dane dla bieżącego widoku).
    Jeśli to bywa irytujące, dorobimy później przełącznik
    „tylko niezsprawdzonych".
    """
    players = filtered_df.rename(columns={
        "Nick": "player_id",
        "Leaguepedia": "overview_page",
    })[["player_id", "overview_page"]].to_dict("records")

    bar = st.progress(0.0, text="Sprawdzam lolpros…")

    def on_progress(done: int, total: int, pid: str) -> None:
        bar.progress(
            done / max(total, 1),
            text=f"Lolpros: {done}/{total} (ostatni: {pid})",
        )

    found = batch_check_lolpros(
        players,
        on_progress=on_progress,
        save=update_lolpros,
    )
    bar.progress(1.0, text="Gotowe.")

    st.session_state["lolpros_msg"] = (
        "ok",
        f"Sprawdzono {len(players)} graczy — znaleziono lolpros dla "
        f"{len(found)}.",
    )
    st.rerun()


# --- TRYB 2: per liga (poprzedni widok) --------------------------------------

def _render_per_league_section() -> None:
    """Sekcja „gracze per liga"  — pobieranie rosterów turniejów."""
    st.header("🏟️ Per liga")
    st.caption(
        "Pobranie robi pełny snapshot rosterów lig z LEAGUE_GROUPS "
        "(skład drużyn zmienia się przy transferach, więc bez kursora). "
        "Jeden gracz może pojawić się w kilku ligach — to osobne wpisy."
    )

    sync = all_players_sync()
    all_leagues = [lg for group in LEAGUE_GROUPS.values() for lg in group]
    n_loaded = sum(
        1 for lg in all_leagues if sync.get(lg, {}).get("last_fetched")
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Unikalnych graczy", count_unique_players())
    m2.metric("Wpisów w bazie", sum(
        count_players_for_league(lg) for lg in all_leagues
    ))
    m3.metric("Ligi wczytane", f"{n_loaded} / {len(all_leagues)}")

    if st.button("⬇️ Wczytaj graczy wszystkich lig",
                 use_container_width=True):
        _fetch_per_league_and_report(all_leagues)

    st.divider()

    # --- per-ligowe statusy z przyciskiem pobierania ---
    for label, leagues in LEAGUE_GROUPS.items():
        st.subheader(label)
        _league_rows(leagues, sync)
        st.write("")

    st.divider()

    # --- tabela graczy z lig (per-ligowych) ---
    st.subheader("Tabela graczy z lig")

    per_league_players = fetch_per_league_players()
    if not per_league_players:
        st.info(
            "Tabela per-ligowa jest pusta — pobierz dane przyciskami powyżej."
        )
        return

    df = pd.DataFrame(per_league_players)
    df = df.rename(columns={
        "player_id":            "Nick",
        "overview_page":        "Leaguepedia",
        "role":                 "Rola",
        "team":                 "Drużyna",
        "league":               "Liga",
        "country":              "Kraj",
        "residency":            "Rezydencja",
        "nationality_primary":  "Narodowość",
        "is_retired":           "Retired",
        "tournament":           "Ostatni turniej",
        "date_start":           "Data startu turnieju",
        "last_fetched":         "Pobrane",
    })
    display_cols = [
        "Nick", "Rola", "Drużyna", "Liga", "Kraj", "Rezydencja",
        "Narodowość", "Retired", "Ostatni turniej",
        "Data startu turnieju", "Leaguepedia", "Pobrane",
    ]
    df = df[display_cols]

    f1, f2, f3 = st.columns(3)
    with f1:
        league_filter = st.multiselect(
            "Filtr lig", sorted(df["Liga"].unique()), default=[]
        )
    with f2:
        roles_available = sorted(r for r in df["Rola"].unique() if r)
        role_filter = st.multiselect(
            "Filtr ról", roles_available, default=[]
        )
    with f3:
        search = st.text_input("Szukaj (nick / drużyna / wiki)", value="")

    filtered = df
    if league_filter:
        filtered = filtered[filtered["Liga"].isin(league_filter)]
    if role_filter:
        filtered = filtered[filtered["Rola"].isin(role_filter)]
    if search.strip():
        s = search.strip().lower()
        mask = (
            filtered["Nick"].str.lower().str.contains(s, na=False)
            | filtered["Drużyna"].str.lower().str.contains(s, na=False)
            | filtered["Leaguepedia"].str.lower().str.contains(s, na=False)
        )
        filtered = filtered[mask]

    st.caption(
        f"{len(filtered)} wpisów (z {len(df)} w bazie). "
        f"Uwaga: ten sam gracz może być w wielu ligach — to osobne wpisy."
    )
    st.dataframe(filtered, use_container_width=True, hide_index=True)


# --- helpery UI --------------------------------------------------------------

def _league_rows(leagues: list[str], sync: dict) -> None:
    """Renderuje nagłówek i po jednym wierszu na ligę z przyciskiem pobrania."""
    header = st.columns(_COLS, vertical_alignment="center")
    for col, title in zip(
        header, ["Liga", "Graczy w bazie", "Ostatnie pobranie", ""]
    ):
        col.caption(title)

    for lg in leagues:
        row = sync.get(lg, {})
        local = count_players_for_league(lg)
        last_fetched = row.get("last_fetched")

        c_name, c_local, c_last, c_btn = st.columns(
            _COLS, vertical_alignment="center"
        )
        c_name.markdown(f"**{lg}**")
        c_local.write(str(local))
        c_last.write(_fmt_dt(last_fetched) if last_fetched else "—")

        label = "↻ Odśwież" if last_fetched else "⬇️ Pobierz"
        if c_btn.button(label, key=f"players_load_{lg}",
                        use_container_width=True):
            _fetch_per_league_and_report([lg])


def _fmt_dt(iso: str) -> str:
    """Skraca znacznik ISO ('2026-05-18T14:30:00') do 'YYYY-MM-DD HH:MM'."""
    return iso.replace("T", " ")[:16]


def _fetch_per_league_and_report(leagues: list[str]) -> None:
    """Pobiera graczy podanych lig z paskiem postępu, zapisuje komunikat,
    przeładowuje stronę.

    Dwie fazy:
      1. Pierwszy przebieg po wszystkich ligach z pauzami
         (_INTER_LEAGUE_PAUSE) — analogicznie do draftów.
      2. Jeśli któraś liga padła (rate-limit / przejściowy MWException),
         odczekaj _RETRY_COOLDOWN i ponów TYLKO te ligi. Udany retry
         nadpisuje wynik z fazy 1, więc raport pokazuje stan końcowy.
    """
    bar = st.progress(0.0, text="Łączę się z Leaguepedia…")
    outcomes = _run_pass(
        leagues, bar, label_prefix="Pobieram graczy",
        progress_offset=0.0, progress_scale=1.0,
    )

    failed = [o.league for o in outcomes if o.error]
    if failed:
        for s in range(int(_RETRY_COOLDOWN), 0, -1):
            bar.progress(
                1.0,
                text=f"{len(failed)} lig padło — ponowię za {s}s…",
            )
            time.sleep(1.0)

        retry_outcomes = _run_pass(
            failed, bar, label_prefix="Ponawiam",
            progress_offset=0.0, progress_scale=1.0,
        )
        by_league = {o.league: o for o in outcomes}
        for o in retry_outcomes:
            by_league[o.league] = o
        outcomes = [by_league[lg] for lg in leagues]

    bar.progress(1.0, text="Gotowe.")
    st.session_state["players_msg"] = _summary(outcomes)
    st.rerun()


def _run_pass(
    leagues: list[str],
    bar,
    *,
    label_prefix: str,
    progress_offset: float,
    progress_scale: float,
) -> list[PlayersFetchOutcome]:
    """Jeden przebieg po liście lig z pauzami między nimi."""
    n = len(leagues)
    outcomes: list[PlayersFetchOutcome] = []
    for i, lg in enumerate(leagues):
        pct = progress_offset + progress_scale * (i / n)
        bar.progress(pct, text=f"{label_prefix} {lg}… ({i + 1}/{n})")
        outcomes.append(fetch_players_for_league(lg))
        if n > 1 and i < n - 1:
            pct = progress_offset + progress_scale * ((i + 1) / n)
            bar.progress(
                pct,
                text=f"Pauza przed kolejną ligą… ({i + 1}/{n} gotowe)",
            )
            time.sleep(_INTER_LEAGUE_PAUSE)
    return outcomes


def _summary(outcomes: list[PlayersFetchOutcome]) -> tuple[str, str]:
    """Buduje (poziom, treść) komunikatu po pobraniu — poziom: ok/warn/err."""
    saved = sum(o.saved for o in outcomes)
    errors = [o for o in outcomes if o.error]

    lines = [
        f"Pobrano ligi: {len(outcomes)} · zapisano {saved} wpisów graczy."
    ]
    for o in errors:
        lines.append(
            f"❌ **{o.league}** — pobieranie przerwał błąd: {o.error}. "
            f"Ponów pobranie później."
        )
    level = "err" if errors else "ok"
    return level, "\n\n".join(lines)
