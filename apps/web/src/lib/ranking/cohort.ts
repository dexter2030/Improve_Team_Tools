/**
 * Kohorty porównawcze: rozkład (mean + std) każdej metryki w grupie
 * (rola × liga × rok × split). Z-score liczymy względem tego rozkładu. Port
 * hidden_gems/scoring.py::_metric_dist, rozbity do grana splitu.
 *
 * Wariancja POPULACYJNA (dzielimy przez n, nie n-1) — kohorta to cała
 * populacja ligi w danym splicie, nie próbka z większej całości. Per-split
 * kohorty są mniejsze niż roczne → częściej lowSample (świadomy kompromis,
 * patrz weights.ts: MIN_COHORT_PLAYERS).
 */

import type { LpPlayerStat } from "@/lib/db/schema";
import {
  MIN_COHORT_PLAYERS,
  SCORED_METRICS,
  type ScoredMetric,
} from "./weights";

export interface MetricDist {
  mean: number;
  std: number;
  n: number;
}

export type CohortKey = string;

export interface Cohort {
  role: string | null;
  league: string;
  year: number;
  split: string;
  nPlayers: number;
  lowSample: boolean;
  dist: Partial<Record<ScoredMetric, MetricDist>>;
}

/** Jednoznaczny klucz (rola, liga, rok, split) — JSON, by uniknąć kolizji separatorów. */
export function cohortKey(
  role: string | null,
  league: string,
  year: number,
  split: string
): CohortKey {
  return JSON.stringify([role, league, year, split]);
}

/**
 * Buduje wszystkie kohorty (rola×liga×rok) z listy sezonów graczy. Jeden sezon
 * gracza = jeden wkład do swojej kohorty — średnia „po graczach", nie „po grach"
 * (zawodnik z wieloma grami nie ciągnie rozkładu pod siebie).
 *
 * Najlepiej karmić to WSZYSTKIMI zsynchowanymi sezonami (nie tylko jedną ligą),
 * żeby sezony z karier w innych ligach też miały pełną kohortę do Z-score.
 */
export function buildCohorts(
  stats: readonly LpPlayerStat[]
): Map<CohortKey, Cohort> {
  const groups = new Map<CohortKey, LpPlayerStat[]>();
  for (const s of stats) {
    const key = cohortKey(s.role, s.league, s.year, s.split);
    const arr = groups.get(key);
    if (arr) arr.push(s);
    else groups.set(key, [s]);
  }

  const out = new Map<CohortKey, Cohort>();
  for (const [key, members] of groups) {
    const sample = members[0];
    const dist: Partial<Record<ScoredMetric, MetricDist>> = {};
    for (const m of SCORED_METRICS) {
      const vals = members
        .map((x) => x[m])
        .filter((v): v is number => v !== null && Number.isFinite(v));
      const d = metricDist(vals);
      if (d) dist[m] = d;
    }
    out.set(key, {
      role: sample.role,
      league: sample.league,
      year: sample.year,
      split: sample.split,
      nPlayers: members.length,
      lowSample: members.length < MIN_COHORT_PLAYERS,
      dist,
    });
  }
  return out;
}

function metricDist(vals: number[]): MetricDist | null {
  const n = vals.length;
  if (n === 0) return null;
  let mean = 0;
  for (const v of vals) mean += v;
  mean /= n;
  let varSum = 0;
  for (const v of vals) varSum += (v - mean) ** 2;
  const std = n > 1 ? Math.sqrt(varSum / n) : 0;
  return { mean, std, n };
}

/** Z-score wartości względem rozkładu; null gdy brak wartości / std = 0. */
export function zScore(
  value: number | null,
  dist: MetricDist | undefined
): number | null {
  if (value === null || dist === undefined || dist.std === 0) return null;
  return (value - dist.mean) / dist.std;
}
