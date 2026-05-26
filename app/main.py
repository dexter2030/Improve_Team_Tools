"""
app/main.py

LoL Scouting Dashboard — UI.

Run with:
    streamlit run app/main.py

Resolves identities live against the Riot API (SoloQ) and Leaguepedia
(pro play). Requires RIOT_API_KEY in a .env file at the project root.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
import streamlit as st

from src.config import bootstrap_secrets

bootstrap_secrets()

from src.api.leaguepedia_client import LeaguepediaClient, ScoreboardRow
from src.api.riot_client import RankedEntry, RiotClient, SqliteCacheStore
from src.processing.champion_stats import ChampionStat, aggregate_champion_stats
from src.cache.profile_store import ProfileStore
from src.processing.links import parse_leaguepedia_url, parse_opgg_url
from src.processing.profiles import (
    ProPlayIdentity,
    ResolutionState,
    Role,
    ScoutingProfile,
    SoloQIdentity,
)
from src.processing.resolver import ProfileResolver, ResolutionResult

from draft_analyzer.draft_analyzer_page import render as render_draft_analyzer
from draft_analyzer.database_page import render as render_database
from draft_analyzer.players_data_page import render as render_players_data
from draft_analyzer.match_data_page import render as render_match_data

from app.settings_page import render as render_settings
from app.soloq_lookup_page import render as render_soloq_lookup
from app.cohort_page import render as render_cohort
from app.auth import require_password

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DB_PATH = PROJECT_ROOT / "scouting.db"

# Light-mode-safe colors used in both the Styler table and HTML badges.
_STATUS: dict[str, tuple[str, str]] = {
    "resolved":   ("#c8e6c9", "#155724"),
    "partial":    ("#fff3cd", "#856404"),
    "failed":     ("#f8d7da", "#721c24"),
    "unresolved": ("#e0e0e0", "#424242"),
}


# --- Visual helpers ----------------------------------------------------------

def _status_badge(state: ResolutionState | str) -> str:
    val = state.value if isinstance(state, ResolutionState) else str(state)
    bg, fg = _STATUS.get(val, ("#e0e0e0", "#424242"))
    return (
        f'<span style="background:{bg}; color:{fg}; padding:2px 12px; '
        f'border-radius:12px; font-size:0.8em; font-weight:700; '
        f'letter-spacing:.05em;">{val.upper()}</span>'
    )


def _highlight_status(val: str) -> str:
    bg, fg = _STATUS.get(val, ("", ""))
    return f"background-color:{bg}; color:{fg}; font-weight:600;" if bg else ""


# --- Resource singletons -----------------------------------------------------

@st.cache_resource
def get_store() -> ProfileStore:
    return ProfileStore(DB_PATH)


@st.cache_resource
def get_resolver() -> ProfileResolver:
    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "RIOT_API_KEY is not set — add it to a .env file "
            "at the project root."
        )
    cache = SqliteCacheStore(DB_PATH)
    return ProfileResolver(
        RiotClient(api_key, cache=cache),
        LeaguepediaClient(cache),
    )


@st.cache_resource
def get_riot_client() -> RiotClient:
    """Shared RiotClient for on-demand stat fetches (ranked, etc.)."""
    api_key = os.environ.get("RIOT_API_KEY")
    if not api_key:
        raise RuntimeError(
            "RIOT_API_KEY is not set — add it to a .env file "
            "at the project root."
        )
    return RiotClient(api_key, cache=SqliteCacheStore(DB_PATH))


@st.cache_resource
def get_leaguepedia_client() -> LeaguepediaClient:
    """Shared LeaguepediaClient for on-demand scoreboard fetches."""
    return LeaguepediaClient(cache=SqliteCacheStore(DB_PATH))


# Friendly labels for the queue types we care about.
_QUEUE_LABELS: dict[str, str] = {
    "RANKED_SOLO_5x5": "SoloQ",
    "RANKED_FLEX_SR":  "Flex",
}

# Tier ordering for display sorting (highest first).
_TIER_ORDER: dict[str, int] = {
    "CHALLENGER": 0, "GRANDMASTER": 1, "MASTER": 2,
    "DIAMOND": 3, "EMERALD": 4, "PLATINUM": 5,
    "GOLD": 6, "SILVER": 7, "BRONZE": 8, "IRON": 9,
}


def _render_ranked_panel(account: SoloQIdentity) -> None:
    """Fetch and render ranked stats for one resolved SoloQ account."""
    if not account.puuid:
        st.caption(
            f"`{account.riot_id}` — not resolved, ranked data unavailable."
        )
        return

    with st.spinner(f"Fetching ranked data for {account.riot_id}…"):
        try:
            entries: list[RankedEntry] = get_riot_client().fetch_ranked(
                account.puuid, account.platform
            )
        except Exception as err:
            st.warning(
                f"Could not fetch ranked data for `{account.riot_id}`: {err}"
            )
            return

    # Keep only SR queues, sorted by tier (highest first).
    entries = [e for e in entries if e.queue_type in _QUEUE_LABELS]
    entries.sort(key=lambda e: _TIER_ORDER.get(e.tier.upper(), 99))

    st.markdown(f"**`{account.riot_id}`** · {account.platform}")
    if not entries:
        st.caption("Unranked — no solo or flex games this season.")
        return

    for entry in entries:
        label = _QUEUE_LABELS.get(entry.queue_type, entry.queue_type)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(label, f"{entry.tier} {entry.rank}")
        c2.metric("LP", entry.lp)
        c3.metric("Win rate", f"{entry.win_rate:.0%}")
        c4.metric("Games", entry.games)


def _render_champion_stats_panel(profile: ScoutingProfile) -> None:
    """Fetch ScoreboardPlayers rows and render per-champion aggregated stats."""
    proplay = profile.proplay
    if proplay is None or not proplay.leaguepedia_link:
        st.caption("No resolved pro-play identity — champion stats unavailable.")
        return

    with st.spinner("Fetching pro-play champion data…"):
        try:
            rows: list[ScoreboardRow] = get_leaguepedia_client().get_player_scoreboard(
                proplay.leaguepedia_link
            )
        except Exception as err:
            st.warning(f"Could not fetch champion data: {err}")
            return

    if not rows:
        st.caption("No pro-play games found in Leaguepedia for this player.")
        return

    stats: list[ChampionStat] = aggregate_champion_stats(rows)
    st.caption(f"{len(rows)} pro games · {len(stats)} unique champions")

    df = pd.DataFrame([
        {
            "Champion":  s.champion,
            "Games":     s.games,
            "W":         s.wins,
            "L":         s.losses,
            "WR%":       f"{s.win_rate:.0%}",
            "Avg K":     s.avg_kills,
            "Avg D":     s.avg_deaths,
            "Avg A":     s.avg_assists,
            "KDA":       s.kda,
            "Avg CS":    s.avg_cs,
        }
        for s in stats
    ])

    def _color_wr(val: str) -> str:
        try:
            pct = int(val.rstrip("%")) / 100
        except (ValueError, AttributeError):
            return ""
        if pct >= 0.60:
            return "background-color:#c8e6c9; color:#155724;"
        if pct <= 0.40:
            return "background-color:#f8d7da; color:#721c24;"
        return ""

    styled = df.style.map(_color_wr, subset=["WR%"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


# --- Helpers -----------------------------------------------------------------

def render_resolution_feedback(result: ResolutionResult) -> None:
    for report in result.reports:
        line = f"**{report.source}** — {report.message}"
        if report.ok:
            st.success(line)
        elif report.outcome.value == "skipped":
            st.info(line)
        else:
            st.error(line)


def profiles_to_dataframe(profiles: list[ScoutingProfile]) -> pd.DataFrame:
    """Flatten profiles into a table for the scouting-list view."""
    rows = []
    for p in profiles:
        n_accounts = len(p.soloq)
        n_resolved = sum(1 for s in p.soloq if s.is_resolved)
        levels = [s.summoner_level for s in p.soloq
                  if s.summoner_level is not None]
        rows.append({
            "Name": p.display_name,
            "Role": p.role.value,
            "Age": p.age if p.age is not None else "—",
            "Country": p.nationality or "—",
            "op.gg": f"{n_resolved}/{n_accounts}" if n_accounts else "—",
            "Top level": max(levels) if levels else "—",
            "Leaguepedia": p.proplay.leaguepedia_link if p.proplay else "—",
            "Team": (
                p.proplay.current_team
                if p.proplay and p.proplay.current_team
                else "—"
            ),
            "Status": p.resolution_state.value,
            "_id": p.profile_id,
        })
    return pd.DataFrame(rows)


# --- Sidebar -----------------------------------------------------------------

def render_sidebar(store: ProfileStore) -> str:
    st.sidebar.title("LoL Scouting")

    profiles = store.list_all()
    total = len(profiles)

    if total:
        status_counts = Counter(p.resolution_state.value for p in profiles)
        role_counts = Counter(p.role.value for p in profiles)

        c1, c2 = st.sidebar.columns(2)
        c1.metric("Tracked", total)
        c2.metric("Resolved", status_counts.get("resolved", 0))

        st.sidebar.markdown("**Resolution status**")
        for state in ("resolved", "partial", "failed", "unresolved"):
            n = status_counts.get(state, 0)
            if n:
                st.sidebar.markdown(
                    f"{_status_badge(state)}&nbsp; {n}",
                    unsafe_allow_html=True,
                )

        st.sidebar.markdown("**By role**")
        role_df = pd.DataFrame(
            {"Players": [role_counts.get(r.value, 0) for r in Role]},
            index=[r.value for r in Role],
        )
        st.sidebar.bar_chart(role_df, height=140)
    else:
        st.sidebar.caption("No players tracked yet.")

    st.sidebar.divider()
    page = st.sidebar.radio(
        "Navigate",
        [
            "Scouting List", "Add Player", "SoloQ Lookup", "Cohort Baseline",
            "Draft Analyzer", "Database",
            "Players Data", "Match Data", "Settings",
        ],
    )
    st.sidebar.divider()
    st.sidebar.caption("Live data — Riot API & Leaguepedia.")
    return page


# --- Page: Add Player --------------------------------------------------------

def page_add_player(store: ProfileStore) -> None:
    st.header("Add player to watchlist")
    st.caption(
        "Paste profile links — they will be verified live "
        "(op.gg → Riot API, Leaguepedia → wiki). Age, country and notes are "
        "your scouting metadata. lolpros is stored as a reference link."
    )

    with st.form("add_player", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            display_name = st.text_input(
                "Player name *", placeholder="Display name"
            )
            role = st.selectbox("Role *", [r.value for r in Role])
            age = st.number_input("Age", min_value=12, max_value=60,
                                  value=18, step=1)
        with col2:
            nationality = st.text_input("Country", placeholder="e.g., Poland")
            leaguepedia_url = st.text_input(
                "Leaguepedia link",
                placeholder="https://lol.fandom.com/wiki/...",
            )
            lolpros_url = st.text_input(
                "lolpros link",
                placeholder="https://lolpros.gg/player/...",
            )

        opgg_raw = st.text_area(
            "op.gg links — one per line", height=120,
            placeholder=("https://op.gg/lol/summoners/euw/Name-TAG\n"
                         "https://op.gg/lol/summoners/kr/Other-TAG"),
        )
        st.caption(
            "Each op.gg link is a separate SoloQ account — add as many as you like."
        )

        notes = st.text_area("Notes", height=120,
                             placeholder="Your scouting notes...")

        submitted = st.form_submit_button("Add and verify", type="primary")

    if not submitted:
        return

    # --- Validation ---
    if not display_name.strip():
        st.error("Player name is required.")
        return

    opgg_lines = [ln.strip() for ln in opgg_raw.splitlines() if ln.strip()]
    lp_url = leaguepedia_url.strip()
    if not opgg_lines and not lp_url:
        st.error(
            "Provide at least one op.gg or Leaguepedia link — "
            "otherwise there's nothing to fetch."
        )
        return

    # --- Parse links into identity blocks ---
    errors: list[str] = []
    soloq_accounts: list[SoloQIdentity] = []
    for line in opgg_lines:
        try:
            riot_id, platform = parse_opgg_url(line)
        except ValueError as err:
            errors.append(str(err))
            continue
        soloq_accounts.append(
            SoloQIdentity(riot_id=riot_id, platform=platform, opgg_url=line)
        )

    proplay: ProPlayIdentity | None = None
    if lp_url:
        try:
            link = parse_leaguepedia_url(lp_url)
            proplay = ProPlayIdentity(
                leaguepedia_link=link, leaguepedia_url=lp_url
            )
        except ValueError as err:
            errors.append(str(err))

    if errors:
        for e in errors:
            st.error(e)
        return

    try:
        profile = ScoutingProfile.create(
            display_name=display_name,
            role=Role(role),
            soloq=tuple(soloq_accounts),
            proplay=proplay,
            age=int(age),
            nationality=nationality.strip() or None,
            lolpros_url=lolpros_url.strip() or None,
            notes=notes,
        )
    except ValueError as err:
        st.error(f"Could not create profile: {err}")
        return

    # --- Resolve identity keys ---
    with st.spinner("Verifying identity against data sources..."):
        result = get_resolver().resolve(profile)

    store.upsert(result.profile)
    st.markdown(
        f"Added **{result.profile.display_name}** &nbsp;"
        f"{_status_badge(result.profile.resolution_state)}",
        unsafe_allow_html=True,
    )
    render_resolution_feedback(result)


# --- Page: Scouting List -----------------------------------------------------

def page_scouting_list(store: ProfileStore) -> None:
    st.header("Tracked players")

    profiles = store.list_all()
    if not profiles:
        st.info("No players tracked yet. Add one from the **Add Player** page.")
        return

    # Summary metrics
    status_counts = Counter(p.resolution_state.value for p in profiles)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total", len(profiles))
    m2.metric("Resolved", status_counts.get("resolved", 0))
    m3.metric("Partial", status_counts.get("partial", 0))
    m4.metric(
        "Failed / Unresolved",
        status_counts.get("failed", 0) + status_counts.get("unresolved", 0),
    )

    st.divider()

    # Filters
    f1, f2 = st.columns(2)
    with f1:
        role_filter = st.multiselect(
            "Filter by role", [r.value for r in Role], default=[]
        )
    with f2:
        status_filter = st.multiselect(
            "Filter by status",
            ["resolved", "partial", "failed", "unresolved"],
            default=[],
        )

    filtered = profiles
    if role_filter:
        filtered = [p for p in filtered if p.role.value in role_filter]
    if status_filter:
        filtered = [p for p in filtered if p.resolution_state.value in status_filter]

    if not filtered:
        st.warning("No players match the current filters.")
        return

    # Styled dataframe — Status column gets color-coded cells.
    df = profiles_to_dataframe(filtered)
    display_df = df.drop(columns=["_id"])
    styled = display_df.style.map(_highlight_status, subset=["Status"])
    st.dataframe(styled, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Inspect / edit a player")

    label_to_id = {
        f"{p.display_name} ({p.role.value})": p.profile_id for p in filtered
    }
    chosen = st.selectbox("Select a player", list(label_to_id.keys()))
    if not chosen:
        return

    profile = store.get(label_to_id[chosen])
    if profile is None:
        st.error("Profile not found — it may have been deleted.")
        return

    # Player detail header
    n_accounts = len(profile.soloq)
    n_resolved = sum(1 for s in profile.soloq if s.is_resolved)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Role", profile.role.value)
    with c2:
        st.markdown(
            "<div style='font-size:.75rem; color:#888; margin-bottom:6px;'>"
            "Status</div>"
            f"{_status_badge(profile.resolution_state)}",
            unsafe_allow_html=True,
        )
    c3.metric(
        "op.gg accounts",
        f"{n_resolved}/{n_accounts}" if n_accounts else "—",
    )
    c4.metric(
        "Team",
        profile.proplay.current_team
        if profile.proplay and profile.proplay.current_team else "—",
    )

    # Ranked stats — one panel per SoloQ account
    with st.expander("Ranked stats", expanded=True):
        if profile.soloq:
            for account in profile.soloq:
                _render_ranked_panel(account)
        else:
            st.caption("No SoloQ accounts on this profile.")

    # Pro-play champion pool
    with st.expander("Pro-play champion pool", expanded=True):
        _render_champion_stats_panel(profile)

    # Links & identity
    with st.expander("Links & identity"):
        if profile.soloq:
            st.markdown("**SoloQ accounts (op.gg)**")
            for acc in profile.soloq:
                level = (
                    f"level {acc.summoner_level}"
                    if acc.summoner_level is not None else "unresolved"
                )
                line = f"- `{acc.riot_id}` ({acc.platform}) — {level}"
                if acc.opgg_url:
                    line += f" · [op.gg]({acc.opgg_url})"
                st.markdown(line)
        if profile.proplay:
            pp = profile.proplay
            st.markdown("**Pro play (Leaguepedia)**")
            state = "verified" if pp.verified else "unverified"
            line = f"- `{pp.leaguepedia_link}` — {state}"
            if pp.leaguepedia_url:
                line += f" · [Leaguepedia]({pp.leaguepedia_url})"
            st.markdown(line)
            if pp.current_team:
                st.markdown(f"- Team: {pp.current_team}")
        if profile.lolpros_url:
            st.markdown(
                f"**lolpros:** [{profile.lolpros_url}]({profile.lolpros_url})"
            )

    # Notes editor
    edited_notes = st.text_area(
        "Scouting notes", value=profile.notes, height=150, key="edit_notes"
    )
    edit_c1, edit_c2, _ = st.columns([1, 1, 2])
    if edit_c1.button("Save notes", type="primary"):
        store.upsert(profile.with_notes(edited_notes))
        st.success("Notes saved.")
        st.rerun()
    if edit_c2.button("Delete player", type="secondary"):
        store.delete(profile.profile_id)
        st.warning(f"Deleted {profile.display_name}.")
        st.rerun()


# --- Main --------------------------------------------------------------------

def main() -> None:
    require_password()
    st.set_page_config(page_title="LoL Scouting Dashboard", layout="wide")
    store = get_store()
    page = render_sidebar(store)

    if page == "Add Player":
        page_add_player(store)
    elif page == "SoloQ Lookup":
        render_soloq_lookup(store, get_riot_client())
    elif page == "Cohort Baseline":
        render_cohort(get_riot_client())
    elif page == "Draft Analyzer":
        render_draft_analyzer()
    elif page == "Database":
        render_database()
    elif page == "Players Data":
        render_players_data()
    elif page == "Match Data":
        render_match_data()
    elif page == "Settings":
        render_settings()
    else:
        page_scouting_list(store)


if __name__ == "__main__":
    main()
