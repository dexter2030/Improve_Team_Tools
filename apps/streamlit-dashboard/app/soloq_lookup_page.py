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

import altair as alt
import pandas as pd
import streamlit as st

from draft_analyzer.db import fetch_soloq_baseline
from draft_analyzer.leagues import LEAGUE_GROUPS
from shared.api.riot_client import (
    PLATFORM_TO_REGION,
    RankedEntry,
    RiotClient,
)
from src.cache.profile_store import ProfileStore
from src.processing.comparison import (
    COMPARABLE_METRICS,
    REGION_PLATFORMS,
    compare_to_cohort,
    filter_by_platform,
    platforms_for_region,
    region_for_platform,
    z_score_sentiment,
)
from shared.processing.match_stats import (
    MatchStats,
    RecentPerformance,
    aggregate_recent,
    compute_match_stats,
)
from src.processing.soloq_aggregates import (
    SoloQChampionStat,
    aggregate_champions,
    aggregate_roles,
    filter_matches_by_champion,
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
    _render_cohort_comparison(summary, per_match, platform)
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


# --- Cohort comparison -------------------------------------------------------

# Mapowanie znormalizowanych ról kohorty (Top/Jungle/Mid/Bot/Support) na
# nazwy Match-V5 (TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY). UI bierze rolę
# dominującą gracza i mapuje ją na rolę kohorty.
_ROLE_M5_TO_COHORT = {
    "TOP": "Top", "JUNGLE": "Jungle", "MIDDLE": "Mid",
    "BOTTOM": "Bot", "UTILITY": "Support",
}


def _render_cohort_comparison(
    summary: RecentPerformance, per_match: list[MatchStats], platform: str,
) -> None:
    """Porównanie do kohorty zbudowanej w zakładce Cohort Baseline."""
    st.markdown("### Compare against cohort")
    st.caption(
        "Compares this player to the cohort built in **Cohort Baseline** — "
        "percentile (where they rank among peers) and Z-score (how far from "
        "the mean, in standard deviations)."
    )

    all_leagues: list[str] = []
    for group in LEAGUE_GROUPS.values():
        all_leagues.extend(group)

    # Dominująca rola gracza → odpowiadająca rola w kohorcie. Pozwalamy
    # zmienić ręcznie (np. flex jungler scoutowany jako mid).
    suggested_role = _dominant_role_label(per_match)
    role_options = ["(any role)", "Top", "Jungle", "Mid", "Bot", "Support"]
    default_role_idx = (
        role_options.index(suggested_role)
        if suggested_role in role_options else 0
    )

    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    with c1:
        leagues = st.multiselect(
            "Cohort leagues",
            options=all_leagues,
            default=st.session_state.get(
                "soloq_compare_leagues", all_leagues
            ),
            key="soloq_compare_leagues",
            help="Pick which leagues from the baseline to compare against. "
                 "All by default — restrict to one tier for tighter comparison.",
        )
    with c2:
        role = st.selectbox(
            "Role filter",
            options=role_options,
            index=default_role_idx,
            help="Default: player's dominant role in this window.",
        )

    roles_arg = None if role == "(any role)" else [role]
    rows = fetch_soloq_baseline(leagues=leagues or None, roles=roles_arg)
    if not rows:
        st.info(
            "No baseline rows for that league/role combination. Build the "
            "cohort first in the **Cohort Baseline** tab."
        )
        return

    # Region filter — meta KR vs EU różni się na tyle, że globalny Z-score
    # myli. Domyślnie kohorta z regionu gracza (gdy są tam wpisy), inaczej
    # globalna; coach może przełączyć.
    region_options = ["Global (all regions)"] + list(REGION_PLATFORMS)
    player_region = region_for_platform(platform)
    default_region = "Global (all regions)"
    if player_region and filter_by_platform(
        rows, platforms_for_region(player_region)
    ):
        default_region = player_region
    with c3:
        region_choice = st.selectbox(
            "Region (cohort)",
            options=region_options,
            index=region_options.index(default_region),
            help="Compare against same-region peers — KR and EU SoloQ have "
                 "different metas, so a cross-region Z-score is misleading. "
                 "Defaults to the player's region when the cohort has it.",
        )

    platforms_arg = (
        None if region_choice.startswith("Global")
        else platforms_for_region(region_choice)
    )
    cohort_rows = filter_by_platform(rows, platforms_arg)
    if not cohort_rows:
        st.info(
            f"No cohort entries from **{region_choice}** for that league/role. "
            f"Switch to *Global* or build more of the cohort."
        )
        return
    # Champion filter (player side). Baseline trzyma agregaty per-konto, bez
    # rozbicia na championy — więc kohorta zostaje na poziomie roli/regionu,
    # a filtr championa zawęża TYLKO okno gracza (np. do jego maina), żeby
    # gry off-champion nie zaszumiały jego liczb.
    champ_options = ["All champions"] + [
        c.champion for c in aggregate_champions(per_match)
    ]
    with c4:
        champ_choice = st.selectbox(
            "Champion (player)",
            options=champ_options,
            index=0,
            help="Restrict the player's window to one champion (e.g. their "
                 "main) so off-champion games don't muddy the averages. The "
                 "cohort stays role/region-level — the baseline has no "
                 "per-champion breakdown yet.",
        )

    if champ_choice == "All champions":
        player_summary = summary
    else:
        player_summary = aggregate_recent(
            filter_matches_by_champion(per_match, champ_choice)
        )

    st.caption(
        f"Comparing **{champ_choice}** ({player_summary.games} games) against "
        f"{len(cohort_rows)} cohort entries · {region_choice}."
    )

    results = compare_to_cohort(player_summary, cohort_rows)

    # Diverging bar chart Z-score — szybki skan mocnych/słabych stron przed
    # szczegółową tabelą.
    _render_zscore_chart(results)

    df = pd.DataFrame([
        {
            "Metric":         r.label,
            "Player":         _fmt_metric(r.metric, r.player_value),
            "Cohort mean":    _fmt_metric(r.metric, r.cohort.mean),
            "Median":         _fmt_metric(r.metric, r.cohort.median),
            "p25 → p75":      (
                f"{_fmt_metric(r.metric, r.cohort.p25)} → "
                f"{_fmt_metric(r.metric, r.cohort.p75)}"
                if r.cohort.p25 is not None else "—"
            ),
            "Percentile":     (
                f"{r.percentile:.0f}" if r.percentile is not None else "—"
            ),
            "Z-score":        (
                f"{r.z_score:+.2f}" if r.z_score is not None else "—"
            ),
        }
        for r in results
    ])

    def _color_z(val: str) -> str:
        try:
            z = float(val)
        except (ValueError, TypeError):
            return ""
        # Negatywne dla "lower is better" już są oznaczone w COMPARABLE_METRICS;
        # tu kolorujemy tylko czysty znak. Niezdarzające się metryki dwukierunkowe
        # są w COMPARABLE_METRICS jako higher_is_better=None — koloru nie tracimy,
        # zostaje neutralna kolumna.
        if z >= 1.0:
            return "background-color:#c8e6c9; color:#155724; font-weight:600;"
        if z <= -1.0:
            return "background-color:#f8d7da; color:#721c24; font-weight:600;"
        return ""

    styled = df.style.map(_color_z, subset=["Z-score"])
    st.dataframe(styled, use_container_width=True, hide_index=True)


def _render_zscore_chart(results: list) -> None:
    """Poziomy diverging bar chart Z-score per metryka.

    Zielone w prawo = powyżej średniej kohorty (lepiej), czerwone w lewo =
    poniżej; szary = metryka bez kierunku (np. dmg taken). Metryki bez
    Z-score (brak danych / std=0) są pomijane. Szybsze do skanowania niż
    tabela poniżej.
    """
    chart_rows = [
        {
            "Metric": r.label,
            "Z": r.z_score,
            "cat": z_score_sentiment(r.higher_is_better, r.z_score),
        }
        for r in results if r.z_score is not None
    ]
    if not chart_rows:
        return
    cdf = pd.DataFrame(chart_rows)
    bars = (
        alt.Chart(cdf)
        .mark_bar()
        .encode(
            x=alt.X("Z:Q", title="Z-score (σ od średniej kohorty)"),
            y=alt.Y("Metric:N", sort="-x", title=None),
            color=alt.Color(
                "cat:N",
                scale=alt.Scale(
                    domain=["good", "bad", "neutral"],
                    range=["#2e7d32", "#c62828", "#9e9e9e"],
                ),
                legend=None,
            ),
            tooltip=[
                alt.Tooltip("Metric:N", title="Metric"),
                alt.Tooltip("Z:Q", title="Z-score", format="+.2f"),
            ],
        )
        .properties(height=max(26 * len(chart_rows), 140))
    )
    zero = (
        alt.Chart(pd.DataFrame({"x": [0]}))
        .mark_rule(color="#888", strokeDash=[4, 4])
        .encode(x="x:Q")
    )
    st.altair_chart(bars + zero, use_container_width=True)


def _dominant_role_label(per_match: list[MatchStats]) -> str:
    """Zwraca rolę kohorty (Top/Jungle/Mid/Bot/Support) dla gracza."""
    from collections import Counter
    roles = Counter(s.role for s in per_match if s.role)
    if not roles:
        return "(any role)"
    most, _ = roles.most_common(1)[0]
    return _ROLE_M5_TO_COHORT.get(most.upper(), "(any role)")


def _fmt_metric(metric_key: str, value: float | int | None) -> str:
    if value is None:
        return "—"
    # Procentowe metryki renderujemy jako %.
    if metric_key in {"winrate", "kp", "first_blood_rate"}:
        try:
            return f"{float(value):.0%}"
        except (ValueError, TypeError):
            return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


# --- Formatting helpers ------------------------------------------------------

def _fmt(value: float | int | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_pct(value: float | None) -> str:
    return f"{value:.0%}" if value is not None else "—"
