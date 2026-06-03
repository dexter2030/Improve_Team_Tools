/**
 * Sync statystyk meczowych jednej ligi: fetch ScoreboardPlayers (okno
 * RANKING_SINCE_YEARS lat) → agregacja per (gracz, rok) → pełna podmiana w
 * lp_player_stats. Mirror drafts/sync.ts::fetchLeague.
 *
 * Fetch jest per liga (jedno paginowane zapytanie obejmuje wszystkich graczy),
 * więc tanio względem rate-limitu Cargo.
 */

import "server-only";

import { fetchScoreboardPlayers } from "@/lib/leaguepedia/scoreboard";
import { aggregatePlayerYears } from "./aggregate";
import { replaceLeagueStats } from "./stats-repository";
import { RANKING_SINCE_YEARS } from "./weights";

export interface StatsFetchOutcome {
  league: string;
  fetched: number; // wierszy meczowych z Cargo
  saved: number; // sezonów (gracz×rok) zapisanych
  error?: string;
}

export async function syncLeagueStats(
  league: string
): Promise<StatsFetchOutcome> {
  try {
    const sinceYear = new Date().getUTCFullYear() - (RANKING_SINCE_YEARS - 1);
    const rows = await fetchScoreboardPlayers(league, { sinceYear });

    const aggregates = aggregatePlayerYears(rows);
    const now = new Date();
    const saved = await replaceLeagueStats(
      league,
      aggregates.map((a) => ({
        overviewPage: a.overviewPage,
        year: a.year,
        league: a.league,
        role: a.role,
        games: a.games,
        wins: a.wins,
        winrate: a.winrate,
        kda: a.kda,
        csPerMin: a.csPerMin,
        dpm: a.dpm,
        kp: a.kp,
        goldShare: a.goldShare,
        syncedAt: now,
      })),
      // Kursor daty pomijamy — okno i tak full-refresh, a wiersz nie niesie
      // pełnej daty meczu (tylko rok). Sync state trzyma lastFetched + count.
      null
    );

    return { league, fetched: rows.length, saved };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { league, fetched: 0, saved: 0, error: msg };
  }
}
