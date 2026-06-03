/**
 * Kompozycja rankingu ligi: ładuje sezony z bazy, buduje kohorty i woła czysty
 * scoring (score.ts). Liczone w locie przy renderze (force-dynamic) — tania
 * arytmetyka, a wagi w weights.ts można stroić bez re-syncu.
 */

import "server-only";

import { buildCohorts } from "./cohort";
import { rankLeague, type RankedPlayer } from "./score";
import { listAllPlayerStats, birthdatesFor } from "./stats-repository";

export type { RankedPlayer } from "./score";

/**
 * Pełny ranking jednej ligi. Kohorty budujemy z WSZYSTKICH zsynchowanych
 * sezonów (cross-league), żeby sezony z karier w innych ligach też miały
 * rzetelny Z-score (potrzebne do trajektorii i awansu). Rankujemy graczy, którzy
 * mają choć jeden sezon w tej lidze.
 */
export async function getLeagueRanking(
  league: string,
  roleFilter?: string
): Promise<RankedPlayer[]> {
  const allStats = await listAllPlayerStats();
  const cohorts = buildCohorts(allStats);

  const inLeague = new Set<string>();
  const byPlayer = new Map<string, (typeof allStats)[number][]>();
  for (const s of allStats) {
    if (s.league === league) inLeague.add(s.overviewPage);
    const arr = byPlayer.get(s.overviewPage);
    if (arr) arr.push(s);
    else byPlayer.set(s.overviewPage, [s]);
  }

  const pages = [...inLeague];
  const birthdates = await birthdatesFor(pages);

  const players = pages.map((page) => ({
    overviewPage: page,
    seasons: byPlayer.get(page) ?? [],
    birthdate: birthdates.get(page) ?? null,
  }));

  return rankLeague({ league, players, cohorts, roleFilter });
}
