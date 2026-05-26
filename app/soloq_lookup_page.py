"""
app/soloq_lookup_page.py

SoloQ Lookup — pełny widok danych jednego gracza z Riot API.

Dwa tryby wyboru:
  1. Ręcznie — wpisz Riot ID + platforma (działa na dowolnego gracza).
  2. Z listy Scouting Profiles — dropdown z dodanych profili.

Po wybraniu konta pobiera:
  - Account-V1 → PUUID + summoner level
  - League-V4  → ranga, LP, WR (SoloQ + Flex)
  - Match-V5   → ostatnie N meczy rankowych
  - (opcjonalnie) timeline każdego meczu → CS@10, GD@15

Z tych meczy liczy: RecentPerformance (średnie), pulę championów,
rozkład ról. Wszystko wyświetla w sekcjach tej zakładki.

`render(store, riot_client)` jest punktem wejścia; app/main.py wywołuje
ją jak inne strony.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.api.riot_client import (
    PLATFORM_TO_REGION,
    RankedEntry,
    RiotClient,
)
from src.cache.profile_store import ProfileStore
from src.processing.match_stats import (
    MatchStats,
    RecentPerformance,
    aggregate_recent,
    compute_match_stats,
)
from src.processing.soloq_aggregates import (
    SoloQChampionStat,
    aggregate_champions,
    aggregate_roles,
)


_QUEUE_LABELS: dict[str, str] = {
    "RANKED_SOLO_5x5": "SoloQ",
    "RANKED_FLEX_SR":  "Flex",
}

_TIER_ORDER: dict[str, int] = {
    "CHALLENGER": 0, "GRANDMASTER": 1, "MASTER": 2,
    "DIAMOND": 3, "EMERALD": 4, "PLATINUM": 5,
    "GOLD": 6, "SILVER": 7, "BRONZE": 8, "IRON": 9,
}

# Default platforms shown in the dropdown — ordered by relevance for the
# coach's scouting scope (EU first), but `PLATFORM_TO_REGION` is the
# source of truth for what RiotClient accepts.
_PLATFORM_OPTIONS = [
    "euw1", "eun1", "kr", "na1", "br1", "tr1", "jp1",
    "la1", "la2", "oc1", "ru",
]


# --- Public entry point ------------------------------------------------------

def render(store: ProfileStore, riot_client: RiotClient) -> None:
    """Renderuje całą zakładkę SoloQ Lookup."""
    st.title("🎯 SoloQ Lookup")
    st.caption(
        "Deep dive into one player's recent SoloQ — rank, lane stats, "
        "champion pool, vision, gold/min, CS@10, GD@15. Pick a player "
        "manually (any Riot ID) or from your Scouting List."
    )

    riot_id, platform, source_label = _input_picker(store)
    if not riot_id or not platform:
        st.info(
            "Pick a player to fetch — either enter a Riot ID manually "
            "or select one of your tracked profiles."
        )
        return

    c1, c2, c3 = st.columns([2, 2, 3])
    n_matches = c1.slider(
        "Recent matches", min_value=5, max_value=100, value=20, step=5,
        help="More matches = more statistical signal, but each match is "
             "one Riot API call (cached for 30 days).",
    )
    include_timeline = c2.checkbox(
        "Include CS@10 / GD@15 (timeline)",
        value=True,
        help="Adds one extra Riot API call per match. Worth it for laning "
             "evaluation; turn off if you're rate-limited.",
    )
    queue_label = c3.selectbox(
        "Queue",
        options=["RANKED_SOLO_5x5 (420)", "RANKED_FLEX_SR (440)", "Any (no filter)"],
        index=0,
    )
    queue_id = {
        "RANKED_SOLO_5x5 (420)": 420,
        "RANKED_FLEX_SR (440)":  440,
        "Any (no filter)":       None,
    }[queue_label]

    if not st.button(
        f"🔄 Fetch SoloQ data for `{riot_id}` ({platform})",
        type="primary", use_container_width=True,
    ):
        return

    st.caption(f"Source: {source_label}")
    _fetch_and_render(
        riot_client=riot_client,
        riot_id=riot_id,
        platform=platform,
        n_matches=n_matches,
        include_timeline=include_timeline,
        queue_id=queue_id,
    )


# --- Player picker (manual / from profiles) ----------------------------------

def _input_picker(store: ProfileStore) -> tuple[str, str, str]:
    """Zwraca (riot_id, platform, source_label).

    Pusty riot_id sygnalizuje „nic nie wybrano".
    """
    mode = st.radio(
        "Player source",
        ["Manual Riot ID", "From Scouting Profiles"],
        horizontal=True,
    )

    if mode == "Manual Riot ID":
        c1, c2 = st.columns([3, 1])
        with c1:
            riot_id = st.text_input(
                "Riot ID",
                placeholder="GameName#TAG  (e.g.  BIN fanboy#qubzx)",
                help="Game name + #tag, exactly as it appears in client / op.gg.",
            )
        with c2:
            platform = st.selectbox(
                "Platform",
                options=_PLATFORM_OPTIONS,
                index=0,
            )
        riot_id = riot_id.strip()
        if riot_id and "#" not in riot_id:
            st.warning("Riot ID must be in 'GameName#TAG' form.")
            return "", platform, "manual"
        return riot_id, platform, "manual entry"

    # --- From profiles ---
    profiles = store.list_all()
    soloq_options: dict[str, tuple[str, str, str]] = {}
    for p in profiles:
        for acc in p.soloq:
            label = f"{p.display_name} ({p.role.value}) — {acc.riot_id} [{acc.platform}]"
            soloq_options[label] = (acc.riot_id, acc.platform, p.display_name)

    if not soloq_options:
        st.info(
            "No SoloQ accounts in your Scouting Profiles — add a player "
            "with an op.gg link first, or use Manual mode."
        )
        return "", "", "no profiles"

    label = st.selectbox("Scouting profile", list(soloq_options.keys()))
    riot_id, platform, display_name = soloq_options[label]
    return riot_id, platform, f"profile: {display_name}"


# --- The actual fetch + render ----------------------------------------------

def _fetch_and_render(
    *,
    riot_client: RiotClient,
    riot_id: str,
    platform: str,
    n_matches: int,
    include_timeline: bool,
    queue_id: int | None,
) -> None:
    platform = platform.strip().lower()
    if platform not in PLATFORM_TO_REGION:
        st.error(
            f"Unknown platform '{platform}'. Known: "
            f"{', '.join(sorted(PLATFORM_TO_REGION))}."
        )
        return

    # 1) Resolve account → PUUID + level
    with st.spinner(f"Resolving Riot ID `{riot_id}`…"):
        try:
            account = riot_client.resolve_account(riot_id, platform)
        except LookupError:
            st.error(
                f"No Riot account found for `{riot_id}` on `{platform}`. "
                f"Double-check spelling and the region."
            )
            return
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:
            st.error(f"Riot API error while resolving account: {exc}")
            return

    _render_account_header(riot_id, platform, account.puuid, account.summoner_level)

    # 2) Ranked entries
    with st.spinner("Fetching ranked entries…"):
        try:
            ranked = riot_client.fetch_ranked(account.puuid, platform)
        except Exception as exc:
            st.warning(f"Could not fetch ranked data: {exc}")
            ranked = []
    _render_ranked_section(ranked)

    # 3) Match IDs
    with st.spinner(f"Fetching {n_matches} recent match IDs…"):
        try:
            # `queue=0` on Match-V5 means "no filter" in practice, but the
            # endpoint requires the parameter to be omitted — pass `count`
            # only when queue is None.
            if queue_id is None:
                match_ids = riot_client.fetch_match_ids(
                    account.puuid, platform, count=n_matches, queue=0,
                )
            else:
                match_ids = riot_client.fetch_match_ids(
                    account.puuid, platform,
                    count=n_matches, queue=queue_id,
                )
        except Exception as exc:
            st.error(f"Failed to fetch match IDs: {exc}")
            return

    if not match_ids:
        st.info("No matches found in the selected queue.")
        return

    # 4) Per-match fetch (with optional timeline) — slow part, show progress.
    per_match = _fetch_per_match_stats(
        riot_client, match_ids, platform, account.puuid,
        include_timeline=include_timeline,
    )
    if not per_match:
        st.warning(
            "Match list was non-empty but no payloads could be reduced "
            "to MatchStats — likely a transient Riot API issue."
        )
        return

    # 5) Aggregate & render
    summary = aggregate_recent(per_match)
    _render_summary_section(summary)
    _render_champion_section(aggregate_champions(per_match))
    _render_role_section(per_match)
    _render_match_table(per_match)


def _fetch_per_match_stats(
    riot_client: RiotClient,
    match_ids: list[str],
    platform: str,
    puuid: str,
    *,
    include_timeline: bool,
) -> list[MatchStats]:
    """Pobiera mecze + opcjonalnie timeline, redukuje do MatchStats.

    Każdy mecz ma własny try/except — pojedynczy padnięty fetch nie zatrzymuje
    reszty. Pasek postępu wyrażony jako i / N po zakończeniu każdego meczu.
    """
    n = len(match_ids)
    bar = st.progress(0.0, text=f"Fetching matches 0/{n}…")
    out: list[MatchStats] = []

    for i, mid in enumerate(match_ids):
        try:
            match = riot_client.fetch_match(mid, platform)
        except Exception:
            match = None
        if not match:
            bar.progress((i + 1) / n, text=f"Fetching matches {i + 1}/{n}…")
            continue

        timeline = None
        if include_timeline:
            try:
                timeline = riot_client.fetch_match_timeline(mid, platform)
            except Exception:
                timeline = None

        stats = compute_match_stats(match, timeline, puuid)
        if stats is not None:
            out.append(stats)
        bar.progress(
            (i + 1) / n,
            text=f"Fetching matches {i + 1}/{n} ({len(out)} kept)…",
        )

    bar.progress(1.0, text=f"Done — {len(out)}/{n} matches loaded.")
    return out


# --- Render sections ---------------------------------------------------------

def _render_account_header(
    riot_id: str, platform: str, puuid: str, summoner_level: int,
) -> None:
    st.subheader(f"{riot_id}  ·  {platform}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Summoner level", summoner_level)
    c2.metric("Platform", platform)
    c3.metric("Region", PLATFORM_TO_REGION.get(platform, "?"))
    with st.expander("PUUID (for debugging)"):
        st.code(puuid, language="text")


def _render_ranked_section(entries: list[RankedEntry]) -> None:
    st.markdown("### Ranked overview")
    entries = [e for e in entries if e.queue_type in _QUEUE_LABELS]
    if not entries:
        st.caption("Unranked — no SoloQ or Flex games this season.")
        return
    entries.sort(key=lambda e: _TIER_ORDER.get(e.tier.upper(), 99))
    for e in entries:
        label = _QUEUE_LABELS.get(e.queue_type, e.queue_type)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(label, f"{e.tier} {e.rank}")
        c2.metric("LP", e.lp)
        c3.metric("Win rate", f"{e.win_rate:.0%}")
        c4.metric("Games", e.games)


def _render_summary_section(summary: RecentPerformance) -> None:
    st.markdown(f"### Recent performance · {summary.games} games")
    if summary.games == 0:
        st.caption("No matches reduced to stats.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(
        "Win rate",
        f"{summary.winrate:.0%}" if summary.winrate is not None else "—",
        f"{summary.wins}W / {summary.games - summary.wins}L",
    )
    c2.metric("KDA", _fmt(summary.kda))
    c3.metric("KP",  _fmt_pct(summary.kp))
    c4.metric("First-blood rate", _fmt_pct(summary.first_blood_rate))

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("CS/min",   _fmt(summary.cs_per_min))
    c6.metric("Gold/min", _fmt(summary.gold_per_min))
    c7.metric("DPM",      _fmt(summary.dpm))
    c8.metric("Dmg taken/min", _fmt(summary.damage_taken_per_min))

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Vision/min", _fmt(summary.vision_per_min))
    c10.metric("Wards/min",  _fmt(summary.wards_per_min))
    c11.metric("CS@10",      _fmt(summary.cs10))
    c12.metric(
        "GD@15",
        _fmt(summary.gd15),
        help="Average gold lead over lane opponent at 15 min "
             "(positive = ahead).",
    )

    c13, _, _, _ = st.columns(4)
    c13.metric("Solo kills (avg)", _fmt(summary.solo_kills))


def _render_champion_section(stats: list[SoloQChampionStat]) -> None:
    st.markdown(f"### Champion pool · {len(stats)} unique")
    if not stats:
        st.caption("No champion data.")
        return

    df = pd.DataFrame([
        {
            "Champion":   s.champion,
            "Games":      s.games,
            "W":          s.wins,
            "L":          s.losses,
            "WR%":        f"{s.win_rate:.0%}",
            "KDA":        s.kda,
            "Avg K":      s.avg_kills,
            "Avg D":      s.avg_deaths,
            "Avg A":      s.avg_assists,
            "CS/min":     s.avg_cs_per_min,
            "Gold/min":   s.avg_gold_per_min,
            "DPM":        s.avg_dpm,
            "Vision/min": s.avg_vision_per_min,
            "KP":         f"{s.avg_kp:.0%}" if s.avg_kp is not None else "—",
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


def _render_role_section(per_match: list[MatchStats]) -> None:
    st.markdown("### Role distribution")
    rows = aggregate_roles(per_match)
    if not rows:
        st.caption("No role data.")
        return
    df = pd.DataFrame([
        {
            "Role":   r.role,
            "Games":  r.games,
            "Wins":   r.wins,
            "WR%":    f"{r.win_rate:.0%}",
            "Share": f"{r.games / len(per_match):.0%}",
        }
        for r in rows
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_match_table(per_match: list[MatchStats]) -> None:
    st.markdown(f"### Per-match breakdown · {len(per_match)} games")
    df = pd.DataFrame([
        {
            "Match ID":   s.match_id,
            "W/L":        "W" if s.win else "L",
            "Champion":   s.champion,
            "Role":       s.role or "—",
            "Dur (min)":  s.duration_min,
            "K":          s.kills,
            "D":          s.deaths,
            "A":          s.assists,
            "KDA":        s.kda,
            "CS":         s.cs,
            "CS/min":     s.cs_per_min,
            "Gold/min":   s.gold_per_min,
            "DPM":        s.dpm,
            "Dmg taken/min": s.damage_taken_per_min,
            "Vision":     s.vision_score,
            "Wards":      s.wards_placed,
            "Wards killed": s.wards_killed,
            "Control wards": s.control_wards_bought,
            "KP":         f"{s.kp:.0%}" if s.kp is not None else "—",
            "CS@10":      s.cs10 if s.cs10 is not None else "—",
            "GD@15":      s.gd15 if s.gd15 is not None else "—",
            "Solo kills": s.solo_kills if s.solo_kills is not None else "—",
            "FB":         "K" if s.first_blood_kill else
                          ("A" if s.first_blood_assist else ""),
        }
        for s in per_match
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


# --- Formatting helpers ------------------------------------------------------

def _fmt(value: float | int | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "—"
