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
from shared.lolpros import batch_check_lolpros
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
        "Leaguepedia player database. Two modes: global (the full Players "
        "table, no league split, with nationality/role filters and lolpros "
        "indicator) and per league (tournament rosters)."
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
    st.header("🌍 All players (global)")
    st.caption(
        "The full `Players` table from Leaguepedia — one row per player, "
        "independent of league. Filter by nationality and role. "
        "The lolpros column shows a link to the lolpros.gg profile if the "
        "player has one (requires a separate click — lolpros is an external "
        "site, the check is done over HTTP)."
    )

    sync_row = get_all_players_global_sync()
    total = count_all_players_global()
    unchecked = count_lolpros_unchecked()

    m1, m2, m3 = st.columns(3)
    m1.metric("Players in DB", total)
    m2.metric(
        "Last fetch",
        _fmt_dt(sync_row["last_fetched"]) if sync_row else "—",
    )
    m3.metric("Unchecked on lolpros", unchecked)

    # Pobieranie — bez filtrów. Filtry na liście (poniżej) działają
    # po stronie klienta, więc raz pobrana baza obsłuży wszystkie.
    if st.button(
        "⬇️ Fetch / refresh global player database",
        use_container_width=True,
        help="Fetches the full Players table from Leaguepedia. May take "
             "a minute — Players has ~30k rows.",
    ):
        _fetch_all_and_report()

    if total == 0:
        st.info("DB is empty — click the button above to fetch.")
        return

    # --- Tabela + filtry ---
    all_players = fetch_all_players_global()
    df = pd.DataFrame(all_players)
    df = df.rename(columns={
        "player_id":            "Name",
        "overview_page":        "Leaguepedia",
        "role":                 "Role",
        "team":                 "Team",
        "country":              "Country",
        "residency":            "Residency",
        "nationality_primary":  "Nationality",
        "is_retired":           "Retired",
        "lolpros_url":          "Lolpros",
        "lolpros_checked_at":   "Lolpros checked",
        "last_fetched":         "Fetched",
    })
    df["Retired"] = df["Retired"].map(
        lambda v: "yes" if str(v).strip() in ("1", "true", "True") else ""
    )

    f1, f2, f3 = st.columns(3)
    with f1:
        countries = sorted(c for c in df["Nationality"].unique() if c)
        nat_filter = st.multiselect(
            "Nationality", countries, default=[],
            help="Filters on Players.NationalityPrimary (country code as "
                 "used by Leaguepedia).",
        )
    with f2:
        roles_available = sorted(r for r in df["Role"].unique() if r)
        role_filter = st.multiselect(
            "Role", roles_available, default=[],
            help="Value from Players.Role on Leaguepedia.",
        )
    with f3:
        only_with_lolpros = st.checkbox(
            "Only with lolpros profile",
            help="Show only players checked on lolpros where a profile was "
                 "found. Unchecked players are hidden.",
        )
        hide_retired = st.checkbox(
            "Hide retired",
        )

    # Rozdzielenie filtrów: "data" (nat/rola/retired) decyduje, kogo w
    # ogóle bierzemy pod uwagę — także do sprawdzania lolpros. "Widok"
    # (tylko z lolprosem) zawęża tabelę, ale NIE wpływa na zakres
    # sprawdzania. Dzięki temu można włączyć „tylko z lolprosem" przed
    # pierwszym sprawdzeniem i nadal kliknąć sprawdź — sprawdzi tych,
    # którzy mają pasującą narodowość/rolę, niezsprawdzonych.
    data_filtered = df
    if nat_filter:
        data_filtered = data_filtered[data_filtered["Nationality"].isin(nat_filter)]
    if role_filter:
        data_filtered = data_filtered[data_filtered["Role"].isin(role_filter)]
    if hide_retired:
        data_filtered = data_filtered[data_filtered["Retired"] == ""]

    # Niezsprawdzeni w obrębie data_filtered — tylu czeka na pukanie.
    # Pusty „Lolpros sprawdzono" = NULL z DB = nigdy nie sprawdzano.
    unchecked = data_filtered[
        data_filtered["Lolpros checked"].isna()
        | (data_filtered["Lolpros checked"] == "")
    ]

    # Widok: opcjonalnie zawężony do tych z lolprosem.
    visible = data_filtered
    if only_with_lolpros:
        visible = visible[visible["Lolpros"].astype(bool)]

    st.caption(
        f"Visible: {len(visible)} · matching filters: "
        f"{len(data_filtered)} · unchecked: {len(unchecked)} "
        f"(DB: {len(df)})."
    )

    # Sprawdzanie idzie na wszystkich pasujących, nawet jeśli filtr
    # „tylko z lolprosem" ukrywa ich w tabeli. Pomijamy już sprawdzonych
    # — nie ma sensu pukać do lolprosa drugi raz.
    a1, a2 = st.columns([3, 1])
    a1.caption(
        "Lolpros check skips already-checked — re-check by clearing the "
        "`lolpros_checked_at` column in DB."
    )
    btn_label = (
        f"🔎 Check lolpros ({len(unchecked)} unchecked)"
        if len(unchecked) > 0
        else "🔎 All matching already checked"
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
    display_df["Lolpros checked"] = display_df["Lolpros checked"].map(
        lambda v: _fmt_dt(v) if v else "—"
    )

    display_cols = [
        "Name", "Role", "Team", "Country", "Residency", "Nationality",
        "Retired", "Leaguepedia", "Lolpros", "Lolpros checked",
    ]
    display_df = display_df[display_cols]

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Leaguepedia": st.column_config.LinkColumn(
                "Leaguepedia",
                display_text="open",
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
    bar = st.progress(0.0, text="Connecting to Leaguepedia…")

    # Players ma rzędu 30k wierszy. Pasek wyrażony w postępie do
    # tej liczby — niedokładny, ale daje feedback (Cargo nie zwraca
    # globalnego totalu, więc bierzemy przybliżenie).
    expected_total = 30000

    def on_progress(total_so_far: int) -> None:
        pct = min(total_so_far / expected_total, 0.95)
        bar.progress(pct, text=f"Fetched {total_so_far} players…")

    outcome = sync_fetch_all_players(on_progress=on_progress)
    bar.progress(1.0, text="Done.")

    if outcome.error:
        st.session_state["players_msg"] = (
            "err",
            f"Global DB fetch failed: {outcome.error}. "
            f"Already-saved rows stay in DB.",
        )
    else:
        st.session_state["players_msg"] = (
            "ok",
            f"Fetched {outcome.fetched} rows, saved "
            f"{outcome.saved} players to global DB.",
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
        "Name": "player_id",
        "Leaguepedia": "overview_page",
    })[["player_id", "overview_page"]].to_dict("records")

    bar = st.progress(0.0, text="Checking lolpros…")

    def on_progress(done: int, total: int, pid: str) -> None:
        bar.progress(
            done / max(total, 1),
            text=f"Lolpros: {done}/{total} (last: {pid})",
        )

    found = batch_check_lolpros(
        players,
        on_progress=on_progress,
        save=update_lolpros,
    )
    bar.progress(1.0, text="Done.")

    st.session_state["lolpros_msg"] = (
        "ok",
        f"Checked {len(players)} players — found lolpros for "
        f"{len(found)}.",
    )
    st.rerun()


# --- TRYB 2: per liga (poprzedni widok) --------------------------------------

def _render_per_league_section() -> None:
    """Sekcja „gracze per liga"  — pobieranie rosterów turniejów."""
    st.header("🏟️ Per league")
    st.caption(
        "Fetch grabs a full snapshot of rosters across LEAGUE_GROUPS "
        "(rosters change at transfers, so no cursor). "
        "One player may appear in several leagues — separate entries."
    )

    sync = all_players_sync()
    all_leagues = [lg for group in LEAGUE_GROUPS.values() for lg in group]
    n_loaded = sum(
        1 for lg in all_leagues if sync.get(lg, {}).get("last_fetched")
    )

    m1, m2, m3 = st.columns(3)
    m1.metric("Unique players", count_unique_players())
    m2.metric("Entries in DB", sum(
        count_players_for_league(lg) for lg in all_leagues
    ))
    m3.metric("Leagues synced", f"{n_loaded} / {len(all_leagues)}")

    if st.button("⬇️ Fetch players of all leagues",
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
    st.subheader("Per-league player table")

    per_league_players = fetch_per_league_players()
    if not per_league_players:
        st.info(
            "Per-league table is empty — fetch data via the buttons above."
        )
        return

    df = pd.DataFrame(per_league_players)
    df = df.rename(columns={
        "player_id":            "Name",
        "overview_page":        "Leaguepedia",
        "role":                 "Role",
        "team":                 "Team",
        "league":               "League",
        "country":              "Country",
        "residency":            "Residency",
        "nationality_primary":  "Nationality",
        "is_retired":           "Retired",
        "tournament":           "Last tournament",
        "date_start":           "Tournament start",
        "last_fetched":         "Fetched",
    })
    display_cols = [
        "Name", "Role", "Team", "League", "Country", "Residency",
        "Nationality", "Retired", "Last tournament",
        "Tournament start", "Leaguepedia", "Fetched",
    ]
    df = df[display_cols]

    f1, f2, f3 = st.columns(3)
    with f1:
        league_filter = st.multiselect(
            "League filter", sorted(df["League"].unique()), default=[]
        )
    with f2:
        roles_available = sorted(r for r in df["Role"].unique() if r)
        role_filter = st.multiselect(
            "Role filter", roles_available, default=[]
        )
    with f3:
        search = st.text_input("Search (name / team / wiki)", value="")

    filtered = df
    if league_filter:
        filtered = filtered[filtered["League"].isin(league_filter)]
    if role_filter:
        filtered = filtered[filtered["Role"].isin(role_filter)]
    if search.strip():
        s = search.strip().lower()
        mask = (
            filtered["Name"].str.lower().str.contains(s, na=False)
            | filtered["Team"].str.lower().str.contains(s, na=False)
            | filtered["Leaguepedia"].str.lower().str.contains(s, na=False)
        )
        filtered = filtered[mask]

    st.caption(
        f"{len(filtered)} entries (of {len(df)} in DB). "
        f"Note: the same player may appear in several leagues — separate entries."
    )
    st.dataframe(filtered, use_container_width=True, hide_index=True)


# --- helpery UI --------------------------------------------------------------

def _league_rows(leagues: list[str], sync: dict) -> None:
    """Renderuje nagłówek i po jednym wierszu na ligę z przyciskiem pobrania."""
    header = st.columns(_COLS, vertical_alignment="center")
    for col, title in zip(
        header, ["League", "Players in DB", "Last fetch", ""]
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

        label = "↻ Refresh" if last_fetched else "⬇️ Fetch"
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
    bar = st.progress(0.0, text="Connecting to Leaguepedia…")
    outcomes = _run_pass(
        leagues, bar, label_prefix="Fetching players",
        progress_offset=0.0, progress_scale=1.0,
    )

    failed = [o.league for o in outcomes if o.error]
    if failed:
        for s in range(int(_RETRY_COOLDOWN), 0, -1):
            bar.progress(
                1.0,
                text=f"{len(failed)} leagues failed — retrying in {s}s…",
            )
            time.sleep(1.0)

        retry_outcomes = _run_pass(
            failed, bar, label_prefix="Retrying",
            progress_offset=0.0, progress_scale=1.0,
        )
        by_league = {o.league: o for o in outcomes}
        for o in retry_outcomes:
            by_league[o.league] = o
        outcomes = [by_league[lg] for lg in leagues]

    bar.progress(1.0, text="Done.")
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
                text=f"Pause before next league… ({i + 1}/{n} done)",
            )
            time.sleep(_INTER_LEAGUE_PAUSE)
    return outcomes


def _summary(outcomes: list[PlayersFetchOutcome]) -> tuple[str, str]:
    """Buduje (poziom, treść) komunikatu po pobraniu — poziom: ok/warn/err."""
    saved = sum(o.saved for o in outcomes)
    errors = [o for o in outcomes if o.error]

    lines = [
        f"Fetched {len(outcomes)} leagues · saved {saved} player entries."
    ]
    for o in errors:
        lines.append(
            f"❌ **{o.league}** — fetch failed: {o.error}. "
            f"Retry later."
        )
    level = "err" if errors else "ok"
    return level, "\n\n".join(lines)
