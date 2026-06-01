"""
app/cohort_page.py

Cohort Baseline — zakładka do budowania bazy referencyjnej graczy z
top lig i ERL.

Trzy kolejne sekcje (workflow):
  1. Scrape lolpros — bierze graczy z lolpros_url (z Players Data),
     wyciąga im listę kont SoloQ ze strony lolpros.gg.
  2. Compute baseline — dla każdego konta (z 100+ gier w sezonie)
     pobiera mecze SoloQ od cutoff sezonu i liczy agregaty.
  3. Browse — tabela baseline z filtrami liga/rola, eksport do
     porównań w zakładce SoloQ Lookup.

Operacje na Riot API są kosztowne; pasek postępu jest obowiązkowy,
a wszystko trafia do cache (SqliteCacheStore) — drugi przejazd nie
zżera API ponownie.
"""

from __future__ import annotations

import time
from datetime import date, datetime, timezone

import pandas as pd
import requests
import streamlit as st

from draft_analyzer.db import (
    accounts_needing_baseline,
    count_all_lolpros_accounts,
    count_lolpros_scraped,
    count_soloq_baseline_for_cutoff,
    fetch_soloq_baseline,
    init_db,
    players_needing_lolpros_scrape,
    upsert_lolpros_accounts,
    upsert_soloq_baseline,
)
from draft_analyzer.leagues import LEAGUE_GROUPS
from shared.lolpros import scrape_lolpros_accounts
from shared.api.riot_client import RiotClient
from src.processing.cohort_baseline import (
    DEFAULT_MIN_SEASON_GAMES,
    compute_account_baseline,
)

# Pauza między żądaniami do lolpros — bądźmy mili dla strony.
_LOLPROS_PAUSE_S = 0.4

# Pauza między fetchami baseline na poziomie konta. Każde konto to ~20-40
# API calli; krótka pauza po zakończeniu konta pomaga "wyrównać" oddech
# rate-limitera.
_BASELINE_INTER_ACCOUNT_PAUSE_S = 0.5


def render(riot_client: RiotClient) -> None:
    """Renderuje całą zakładkę Cohort Baseline."""
    init_db()
    st.title("📊 Cohort Baseline")
    st.caption(
        "Build a reference cohort of pro-scene SoloQ players from Tier 1 + "
        "ERL leagues. Used by the SoloQ Lookup tab to compare your manually "
        "added prospects against peers (percentiles, Z-scores per role/league)."
    )

    leagues = _league_picker()
    cutoff_epoch = _cutoff_picker()

    st.divider()
    _section_scrape_lolpros(leagues)

    st.divider()
    _section_compute_baseline(riot_client, cutoff_epoch)

    st.divider()
    _section_browse_baseline(leagues, cutoff_epoch)


# --- League + cutoff pickers ------------------------------------------------

def _league_picker() -> list[str]:
    """Multiselect lig + szybkie szortery dla pelnych grup."""
    all_leagues: list[str] = []
    for group in LEAGUE_GROUPS.values():
        all_leagues.extend(group)

    st.markdown("**League filter** (applies to scrape, compute, and browse)")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Tier 1", use_container_width=True):
        st.session_state["cohort_leagues"] = LEAGUE_GROUPS[
            "Tier 1 — major i wydarzenia międzynarodowe"
        ]
    if c2.button("ERL D1", use_container_width=True):
        st.session_state["cohort_leagues"] = LEAGUE_GROUPS[
            "ERL — pierwsze dywizje (ERL 1)"
        ]
    if c3.button("ERL D2", use_container_width=True):
        st.session_state["cohort_leagues"] = LEAGUE_GROUPS[
            "ERL — drugie dywizje (ERL 2)"
        ]
    if c4.button("All", use_container_width=True):
        st.session_state["cohort_leagues"] = all_leagues

    return st.multiselect(
        "Leagues",
        options=all_leagues,
        default=st.session_state.get("cohort_leagues", all_leagues),
        key="cohort_leagues_picker",
    )


def _cutoff_picker() -> int:
    """Date input → epoch seconds. Default: 1 stycznia 2026 (rok rankowy)."""
    default = date(2026, 1, 1)
    picked = st.date_input(
        "Season cutoff (matches AFTER this date are included)",
        value=default,
        help="Riot Match-V5 has no built-in 'season' filter — we pass this "
             "date as startTime. Pick the date your relevant split started.",
    )
    return int(datetime(picked.year, picked.month, picked.day,
                        tzinfo=timezone.utc).timestamp())


# --- Section 1: scrape lolpros ----------------------------------------------

def _section_scrape_lolpros(leagues: list[str]) -> None:
    """Scrapuje konta z lolpros dla graczy bez kont w lolpros_accounts."""
    st.header("1. Scrape lolpros accounts")
    st.caption(
        "For every player in Players Data who has a `lolpros_url` and "
        "hasn't been scraped yet, we read their lolpros.gg page and pull "
        "out all SoloQ accounts (Riot ID + region). Players without a "
        "lolpros profile are skipped — explicit by design."
    )

    pending = players_needing_lolpros_scrape()
    pending_filtered = _filter_by_league(pending, leagues)

    scraped = count_lolpros_scraped()
    accounts_total = count_all_lolpros_accounts()

    m1, m2, m3 = st.columns(3)
    m1.metric("Players scraped", scraped)
    m2.metric("Accounts collected", accounts_total)
    m3.metric("Pending in league filter", len(pending_filtered))

    if not pending_filtered:
        st.success("All players in the selected leagues have been scraped.")
        return

    if st.button(
        f"🔎 Scrape lolpros for {len(pending_filtered)} players",
        use_container_width=True,
        type="primary",
    ):
        _run_lolpros_scrape(pending_filtered)


def _run_lolpros_scrape(players: list[dict]) -> None:
    n = len(players)
    bar = st.progress(0.0, text=f"Scraping 0/{n}…")
    sess = requests.Session()
    found_count = 0
    error_count = 0
    try:
        for i, p in enumerate(players, start=1):
            url = p.get("lolpros_url") or ""
            page = p.get("overview_page") or ""
            if not url or not page:
                continue
            try:
                accounts = scrape_lolpros_accounts(url, session=sess)
                err = None
            except Exception as exc:
                accounts = []
                err = str(exc)
                error_count += 1

            if accounts:
                upsert_lolpros_accounts(
                    page,
                    [
                        {
                            "game_name": a.game_name,
                            "tag_line":  a.tag_line,
                            "region":    a.region,
                            "platform":  a.platform,
                        }
                        for a in accounts
                    ],
                )
                found_count += len(accounts)
            else:
                upsert_lolpros_accounts(page, [], scrape_error=err)

            bar.progress(
                i / n,
                text=f"Scraping {i}/{n} — collected {found_count} accounts…",
            )
            if i < n:
                time.sleep(_LOLPROS_PAUSE_S)
    finally:
        sess.close()
    bar.progress(1.0, text="Done.")
    st.success(
        f"Scraped {n} players · collected {found_count} accounts "
        f"({error_count} errors)."
    )
    st.rerun()


# --- Section 2: compute baseline --------------------------------------------

def _section_compute_baseline(
    riot_client: RiotClient, cutoff_epoch: int,
) -> None:
    """Bierze konta scrap'owane i liczy im baseline z Riot API."""
    st.header("2. Compute SoloQ baseline (Riot API)")
    st.caption(
        f"For every scraped account with ≥{DEFAULT_MIN_SEASON_GAMES} games "
        "in current SoloQ, fetch all matches after the cutoff and reduce "
        "them to averaged metrics (KDA, CS/min, DPM, Gold/min, Vision/min, "
        "KP, CS@10, GD@15, solo kills, first-blood rate). One row per "
        "(player_account, cutoff)."
    )

    pending = accounts_needing_baseline(cutoff_epoch)
    have_baseline = count_soloq_baseline_for_cutoff(cutoff_epoch)
    total_accounts = count_all_lolpros_accounts()

    m1, m2, m3 = st.columns(3)
    m1.metric("Accounts in DB", total_accounts)
    m2.metric(f"Baseline @ cutoff", have_baseline)
    m3.metric("Pending @ cutoff", len(pending))

    c1, c2, c3 = st.columns([1, 1, 1])
    with c1:
        include_timeline = st.checkbox(
            "Include CS@10 / GD@15", value=True,
            help="Adds one extra Riot API call per match — disable to "
                 "speed things up at the cost of laning metrics.",
        )
    with c2:
        min_games = st.number_input(
            "Min season games", value=DEFAULT_MIN_SEASON_GAMES,
            min_value=10, max_value=500, step=10,
        )
    with c3:
        max_to_run = st.number_input(
            "Limit to N accounts (this run)",
            value=min(50, len(pending)) or 1,
            min_value=1, max_value=max(len(pending), 1), step=1,
            help="Riot API is slow — run in batches; cached responses "
                 "make subsequent runs much faster.",
        )

    if not pending:
        st.success("All scraped accounts have baseline for this cutoff.")
        return

    if st.button(
        f"⬇️ Fetch baseline for {min(int(max_to_run), len(pending))} accounts",
        use_container_width=True,
        type="primary",
    ):
        batch = pending[: int(max_to_run)]
        _run_baseline_compute(
            riot_client, batch, cutoff_epoch,
            include_timeline=include_timeline,
            min_season_games=int(min_games),
        )


def _run_baseline_compute(
    riot_client: RiotClient,
    accounts: list[dict],
    cutoff_epoch: int,
    *,
    include_timeline: bool,
    min_season_games: int,
) -> None:
    n = len(accounts)
    outer = st.progress(0.0, text=f"Account 0/{n}…")
    inner = st.progress(0.0, text="Waiting…")

    saved = 0
    skipped = 0
    no_account = 0
    no_matches = 0
    errors = 0

    for i, acc in enumerate(accounts, start=1):
        outer.progress(
            (i - 1) / n,
            text=f"Account {i}/{n}: {acc['game_name']}#{acc['tag_line']} "
                 f"[{acc['platform']}]",
        )

        def _on_match(done: int, total: int) -> None:
            inner.progress(
                done / max(total, 1),
                text=f"  matches {done}/{total}",
            )

        try:
            outcome = compute_account_baseline(
                overview_page=acc["overview_page"],
                game_name=acc["game_name"],
                tag_line=acc["tag_line"],
                platform=acc["platform"],
                league=acc.get("league"),
                role_hint=acc.get("role"),
                since_epoch=cutoff_epoch,
                riot_client=riot_client,
                include_timeline=include_timeline,
                min_season_games=min_season_games,
                on_match=_on_match,
            )
        except Exception as exc:
            errors += 1
            inner.progress(1.0, text=f"  ERROR: {exc}")
            continue

        if outcome.status == "ok" and outcome.row is not None:
            upsert_soloq_baseline(outcome.row)
            saved += 1
        elif outcome.status == "skipped":
            skipped += 1
        elif outcome.status == "no_account":
            no_account += 1
        elif outcome.status == "no_matches":
            no_matches += 1
        else:
            errors += 1

        if i < n:
            time.sleep(_BASELINE_INTER_ACCOUNT_PAUSE_S)

    outer.progress(1.0, text="Done.")
    inner.progress(1.0, text="Done.")
    st.success(
        f"Processed {n} accounts · saved {saved} · "
        f"skipped (low games) {skipped} · no account {no_account} · "
        f"no matches {no_matches} · errors {errors}."
    )
    st.rerun()


# --- Section 3: browse baseline ---------------------------------------------

def _section_browse_baseline(leagues: list[str], cutoff_epoch: int) -> None:
    st.header("3. Browse cohort")
    rows = fetch_soloq_baseline(
        leagues=leagues or None,
        since_epoch=cutoff_epoch,
    )
    st.caption(
        f"{len(rows)} baseline rows for cutoff "
        f"{datetime.fromtimestamp(cutoff_epoch, tz=timezone.utc).date()} "
        f"and leagues {', '.join(leagues) if leagues else '(all)'}."
    )
    if not rows:
        st.info(
            "No baseline rows for this cutoff/leagues combination. "
            "Run sections 1 and 2 first."
        )
        return

    role_filter = st.multiselect(
        "Role filter",
        options=sorted({r["role"] for r in rows if r.get("role")}),
        default=[],
    )
    if role_filter:
        rows = [r for r in rows if r.get("role") in role_filter]

    df = pd.DataFrame([
        {
            "Player":        r.get("overview_page"),
            "Account":       f"{r.get('game_name')}#{r.get('tag_line')}",
            "Platform":      r.get("platform"),
            "League":        r.get("league") or "—",
            "Role":          r.get("role") or "—",
            "Tier":          f"{r.get('tier') or '—'} {r.get('rank') or ''}".strip(),
            "LP":            r.get("lp"),
            "Games (window)": r.get("games"),
            "WR%":           _pct(r.get("winrate")),
            "KDA":           r.get("kda"),
            "CS/min":        r.get("cs_per_min"),
            "Gold/min":      r.get("gold_per_min"),
            "DPM":           r.get("dpm"),
            "Vision/min":    r.get("vision_per_min"),
            "KP":            _pct(r.get("kp")),
            "CS@10":         r.get("cs10"),
            "GD@15":         r.get("gd15"),
            "Solo K":        r.get("solo_kills"),
            "FB rate":       _pct(r.get("first_blood_rate")),
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


# --- Helpers ----------------------------------------------------------------

def _filter_by_league(
    players: list[dict], leagues: list[str],
) -> list[dict]:
    """Filtruje listę graczy do podanych lig (po podciągu nazwy).

    Pusta lista lig → zwraca wszystkich (brak filtra).
    """
    if not leagues:
        return players
    lower_leagues = [lg.lower() for lg in leagues]

    def _match(player_league: str | None) -> bool:
        if not player_league:
            return False
        pl = player_league.lower()
        return any(lg in pl for lg in lower_leagues)

    return [p for p in players if _match(p.get("league"))]


def _pct(value) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.0%}"
    except (TypeError, ValueError):
        return "—"
