"""
src/processing/match_stats.py

Derives per-match scouting metrics from raw Match-V5 payloads.

This is `src/processing/`, not `src/api/` — the work here is normalization:
turning raw Riot DTOs into the typed numbers a scout reads (KDA, CS/min,
DPM, KP, CS@10, GD@15). The api/ layer hands over `match` and `timeline`
exactly as the API returns them.

Two entry points:
  * `compute_match_stats(match, timeline, puuid)` — one match's metrics
        as a `MatchStats` dataclass; None when the puuid isn't in the
        participant list.
  * `aggregate_recent(stats)` — averages a list of per-match results
        into a single `RecentPerformance`.

Both functions are pure: no I/O, no Riot client, fully testable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


@dataclass(frozen=True, slots=True)
class MatchStats:
    """Per-match metrics for one player; numbers ready for averaging."""
    match_id: str
    win: bool
    kills: int
    deaths: int
    assists: int
    kda: float
    cs: int
    cs_per_min: float
    dpm: float
    kp: float | None        # None when team kills == 0 (no kills team-wide)
    cs10: int | None        # None when timeline missing/short
    gd15: int | None        # None when opponent can't be identified
    duration_min: float
    queue_id: int | None


@dataclass(frozen=True, slots=True)
class RecentPerformance:
    """Averaged scouting metrics across a window of recent matches."""
    games: int
    wins: int
    winrate: float | None
    kda: float | None
    cs_per_min: float | None
    dpm: float | None
    kp: float | None
    cs10: float | None
    gd15: float | None


# --- Per-match ---------------------------------------------------------------

def compute_match_stats(
    match: dict,
    timeline: dict | None,
    puuid: str,
) -> MatchStats | None:
    """Reduce one Match-V5 payload (+ optional timeline) to typed metrics.

    Returns None if `puuid` isn't a participant in `match` (rare, but
    happens for malformed/legacy payloads). When the timeline is missing
    or too short, CS@10 / GD@15 are returned as None — the match-level
    aggregates are still computed.
    """
    me = _participant_for_puuid(match, puuid)
    if me is None:
        return None

    info = match.get("info", {}) or {}
    duration_min = max((info.get("gameDuration", 0) or 0) / 60.0, 1.0)

    kills = me.get("kills", 0) or 0
    deaths = me.get("deaths", 0) or 0
    assists = me.get("assists", 0) or 0
    cs = ((me.get("totalMinionsKilled", 0) or 0)
          + (me.get("neutralMinionsKilled", 0) or 0))
    damage = me.get("totalDamageDealtToChampions", 0) or 0

    team_kills = sum(
        (p.get("kills", 0) or 0)
        for p in info.get("participants", [])
        if p.get("teamId") == me.get("teamId")
    )

    kda = (kills + assists) / max(deaths, 1)
    dpm = damage / duration_min
    cs_per_min = cs / duration_min
    kp = (kills + assists) / team_kills if team_kills else None

    cs10: int | None = None
    gd15: int | None = None
    if timeline:
        my_pid = me.get("participantId")
        opp = _opponent_lane_participant(match, me)
        opp_pid = opp.get("participantId") if opp else None

        f10 = _frame_at(timeline, 10)
        if f10 and my_pid is not None:
            mine = f10.get("participantFrames", {}).get(str(my_pid), {})
            cs10 = _cs_from_pframe(mine)

        f15 = _frame_at(timeline, 15)
        if f15 and my_pid is not None and opp_pid is not None:
            mine = f15.get("participantFrames", {}).get(str(my_pid), {})
            theirs = f15.get("participantFrames", {}).get(str(opp_pid), {})
            if mine and theirs:
                gd15 = ((mine.get("totalGold", 0) or 0)
                        - (theirs.get("totalGold", 0) or 0))

    return MatchStats(
        match_id=(match.get("metadata", {}) or {}).get("matchId", ""),
        win=bool(me.get("win")),
        kills=kills,
        deaths=deaths,
        assists=assists,
        kda=round(kda, 3),
        cs=cs,
        cs_per_min=round(cs_per_min, 2),
        dpm=round(dpm, 1),
        kp=round(kp, 3) if kp is not None else None,
        cs10=cs10,
        gd15=gd15,
        duration_min=round(duration_min, 1),
        queue_id=info.get("queueId"),
    )


# --- Aggregate ---------------------------------------------------------------

def aggregate_recent(stats: Sequence[MatchStats]) -> RecentPerformance:
    """Average a window of per-match results into one RecentPerformance.

    Each numeric metric is averaged across matches that have it populated
    (None values skipped). An empty input yields zero games and all-None
    metrics — callers can decide what "no data" means in their UI.
    """
    games = len(stats)
    if games == 0:
        return RecentPerformance(
            games=0, wins=0, winrate=None,
            kda=None, cs_per_min=None, dpm=None,
            kp=None, cs10=None, gd15=None,
        )

    wins = sum(1 for s in stats if s.win)

    def _avg(key: str) -> float | None:
        vals = [getattr(s, key) for s in stats
                if getattr(s, key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    return RecentPerformance(
        games=games,
        wins=wins,
        winrate=round(wins / games, 3),
        kda=_avg("kda"),
        cs_per_min=_avg("cs_per_min"),
        dpm=_avg("dpm"),
        kp=_avg("kp"),
        cs10=_avg("cs10"),
        gd15=_avg("gd15"),
    )


# --- Helpers (private) ------------------------------------------------------

def _participant_for_puuid(match: dict, puuid: str) -> dict | None:
    for p in (match.get("info", {}) or {}).get("participants", []):
        if p.get("puuid") == puuid:
            return p
    return None


def _opponent_lane_participant(match: dict, me: dict) -> dict | None:
    """Find the lane-opposite participant on the enemy team.

    Match-V5 carries `teamPosition` (normalized post-game) and
    `individualPosition` (best-effort during the game). We try the more
    reliable `teamPosition` first.
    """
    my_team = me.get("teamId")
    my_pos = me.get("teamPosition") or me.get("individualPosition")
    if not my_pos:
        return None
    for p in (match.get("info", {}) or {}).get("participants", []):
        if p.get("teamId") == my_team:
            continue
        pos = p.get("teamPosition") or p.get("individualPosition")
        if pos == my_pos:
            return p
    return None


def _frame_at(timeline: dict, minute: int) -> dict | None:
    """Frame closest to `minute` in a Match-V5 timeline.

    Riot emits one frame per minute; index N is the frame at minute N
    (frame 0 is game start). Returns None when the game ended before
    that minute (early FF) or the timeline is malformed.
    """
    frames = (timeline.get("info", {}) or {}).get("frames", [])
    if 0 <= minute < len(frames):
        return frames[minute]
    return None


def _cs_from_pframe(pf: dict) -> int:
    return ((pf.get("minionsKilled", 0) or 0)
            + (pf.get("jungleMinionsKilled", 0) or 0))
