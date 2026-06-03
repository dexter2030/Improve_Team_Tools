/**
 * Kompozycja rankingu: ładuje sezony z bazy, buduje kohorty i woła czysty
 * scoring (score.ts). Liczone w locie przy renderze (force-dynamic) — tania
 * arytmetyka, a wagi w weights.ts można stroić bez re-syncu.
 */

import "server-only";

import { buildCohorts } from "./cohort";
import { rankLeague, type PlayerCareer, type RankedPlayer } from "./score";
import {
  listAllPlayerStats,
  birthdatesFor,
  pagesByNationality,
} from "./stats-repository";

export type { RankedPlayer } from "./score";

export interface RankingOptions {
  /** Dolna granica lat (włącznie). Brak → bez dolnego ograniczenia. */
  yearFrom?: number;
  /** Górna granica lat (włącznie). Brak → bez górnego ograniczenia. */
  yearTo?: number;
}

/** Predykat „rok w wybranym zakresie" (brzegi opcjonalne). */
function yearPredicate({ yearFrom, yearTo }: RankingOptions) {
  return (year: number) =>
    (yearFrom === undefined || year >= yearFrom) &&
    (yearTo === undefined || year <= yearTo);
}

/**
 * Pełny ranking jednej ligi. Kohorty budujemy z WSZYSTKICH zsynchowanych
 * sezonów (cross-league), żeby sezony z karier w innych ligach też miały
 * rzetelny Z-score (potrzebne do trajektorii i awansu). Rankujemy graczy, którzy
 * mają choć jeden sezon w tej lidze.
 *
 * Filtr lat (opts) zawęża TYLKO sezony gracza wchodzące do oceny i wykresu —
 * baza porównawcza (kohorty) zostaje pełna, więc Z-score sezonu jest stabilny
 * niezależnie od wybranego okna.
 */
export async function getLeagueRanking(
  league: string,
  opts: RankingOptions = {}
): Promise<RankedPlayer[]> {
  const allStats = await listAllPlayerStats();
  const cohorts = buildCohorts(allStats);
  const inRange = yearPredicate(opts);

  const inLeague = new Set<string>();
  const byPlayer = new Map<string, (typeof allStats)[number][]>();
  for (const s of allStats) {
    if (!inRange(s.year)) continue;
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

  return rankLeague({ league, players, cohorts });
}

/**
 * Ranking graczy danej narodowości — cross-league. Każdy gracz jest oceniany w
 * kontekście swojej NAJNOWSZEJ (zsynchronizowanej) ligi: rating z sezonów w tej
 * lidze, sygnały dominacji/awansu z całej (przefiltrowanej) kariery. Wyniki ze
 * wszystkich lig scalamy i sortujemy malejąco po ocenie. Reużywa rankLeague().
 *
 * Ranking obejmuje tylko graczy, którzy mają zsynchowane staty w jakiejś lidze —
 * Polak z niezsynchronizowanej ligi nie ma czego porównać i się nie pojawi.
 */
export async function getNationalityRanking(
  country: string,
  opts: RankingOptions = {}
): Promise<RankedPlayer[]> {
  const [allStats, pages] = await Promise.all([
    listAllPlayerStats(),
    pagesByNationality(country),
  ]);
  if (pages.length === 0) return [];

  const cohorts = buildCohorts(allStats);
  const pageSet = new Set(pages);
  const inRange = yearPredicate(opts);

  const byPlayer = new Map<string, (typeof allStats)[number][]>();
  for (const s of allStats) {
    if (!pageSet.has(s.overviewPage) || !inRange(s.year)) continue;
    const arr = byPlayer.get(s.overviewPage);
    if (arr) arr.push(s);
    else byPlayer.set(s.overviewPage, [s]);
  }
  if (byPlayer.size === 0) return [];

  const birthdates = await birthdatesFor([...byPlayer.keys()]);

  // Każdy gracz trafia do koszyka swojej najnowszej ligi; rankLeague liczy
  // ocenę w kontekście właśnie tej ligi (rating, dominacja, lowSample).
  const buckets = new Map<string, PlayerCareer[]>();
  for (const [page, seasons] of byPlayer) {
    const latest = seasons.reduce((a, b) => (b.year > a.year ? b : a));
    const career: PlayerCareer = {
      overviewPage: page,
      seasons,
      birthdate: birthdates.get(page) ?? null,
    };
    const arr = buckets.get(latest.league);
    if (arr) arr.push(career);
    else buckets.set(latest.league, [career]);
  }

  const merged: RankedPlayer[] = [];
  for (const [league, players] of buckets) {
    merged.push(...rankLeague({ league, players, cohorts }));
  }
  merged.sort((a, b) => b.rating - a.rating || b.potential - a.potential);
  return merged;
}
