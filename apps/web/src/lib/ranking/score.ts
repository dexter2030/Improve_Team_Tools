/**
 * Sedno scoringu: z sezonów gracza (cohort-normalized Z-score) liczymy
 * OCENĘ ogólną (rating 0..100 + tier) i POTENCJAŁ (0..100 + etykieta).
 *
 * Czysta logika — bez DB, bez sieci (testowalne w izolacji). Warstwa wyżej
 * (ranking/index.ts) ładuje sezony z lp_player_stats, buduje kohorty i woła
 * rankLeague().
 *
 * KAWEAT (jak w hidden_gems/scoring.py): surowe metryki nie są porównywalne
 * między ligami — DLATEGO normalizujemy per (rola, liga, rok). „Potencjał" to
 * przejrzysta heurystyka (trajektoria + wiek + dominacja + awans), NIE predykcja.
 */

import { leagueStrength, strengthNorm } from "@/lib/leaguepedia/leagues";
import {
  cohortKey,
  zScore,
  type Cohort,
  type CohortKey,
} from "./cohort";
import {
  AGE_CURVE,
  ASCENSION_SCALE,
  LOGISTIC_K,
  MIN_SEASON_GAMES,
  POTENTIAL_LABELS,
  POTENTIAL_WEIGHTS,
  RECENCY_DECAY,
  SAMPLE_CAP,
  SCORED_METRICS,
  TIER_THRESHOLDS,
  TRAJECTORY_CLAMP,
} from "./weights";

/** Minimalny kształt sezonu (zgodny strukturalnie z LpPlayerStat). */
export interface SeasonStat {
  year: number;
  league: string;
  role: string | null;
  games: number;
  kda: number | null;
  csPerMin: number | null;
  dpm: number | null;
  kp: number | null;
  goldShare: number | null;
}

export interface PlayerCareer {
  overviewPage: string;
  seasons: SeasonStat[]; // wszystkie ligi/lata, jakie mamy w bazie
  birthdate: Date | null;
}

export interface SeasonScore {
  year: number;
  league: string;
  yearZ: number | null;
  games: number;
}

export interface RankedPlayer {
  overviewPage: string;
  league: string; // liga, w której gracz jest rankowany (najnowsza dla rankingu narodowości)
  role: string | null;
  age: number | null;
  games: number; // suma gier w rankowanej lidze
  rating: number; // 0..100
  ratingZ: number;
  tier: string;
  potential: number; // 0..100
  potentialZ: number;
  potentialLabel: string;
  lowSample: boolean;
  perYear: SeasonScore[];
}

// --- Composite Z pojedynczego sezonu ---------------------------------------

/** Średnia dostępnych Z-score'ów metryk sezonu w jego kohorcie; null gdy brak. */
export function composeYearZ(
  season: SeasonStat,
  cohorts: Map<CohortKey, Cohort>
): number | null {
  const cohort = cohorts.get(cohortKey(season.role, season.league, season.year));
  if (!cohort) return null;
  const zs: number[] = [];
  for (const m of SCORED_METRICS) {
    const z = zScore(season[m], cohort.dist[m]);
    if (z !== null) zs.push(z);
  }
  if (zs.length === 0) return null;
  return zs.reduce((a, b) => a + b, 0) / zs.length;
}

// --- Ranking ligi -----------------------------------------------------------

export function rankLeague(params: {
  league: string;
  players: readonly PlayerCareer[];
  cohorts: Map<CohortKey, Cohort>;
  roleFilter?: string;
}): RankedPlayer[] {
  const { league, players, cohorts, roleFilter } = params;
  const out: RankedPlayer[] = [];

  for (const p of players) {
    const inLeague = p.seasons.filter((s) => s.league === league);
    if (inLeague.length === 0) continue;

    const latestInLeague = inLeague.reduce((a, b) => (b.year > a.year ? b : a));
    const role = latestInLeague.role;
    if (roleFilter && role !== roleFilter) continue;

    const careerLatestYear = p.seasons.reduce((m, s) => Math.max(m, s.year), 0);

    // --- Ocena ogólna: sezony w TEJ lidze, ważone recency × próbą ---
    let sw = 0;
    let swz = 0;
    let gamesInLeague = 0;
    for (const s of inLeague) {
      gamesInLeague += s.games;
      const z = composeYearZ(s, cohorts);
      if (z === null) continue;
      const w =
        recencyWeight(s.year, latestInLeague.year) * sampleWeight(s.games);
      sw += w;
      swz += w * z;
    }
    if (sw === 0) continue; // brak policzalnego Z — nie da się ocenić
    const ratingZ = swz / sw;

    // --- Per-rok (cała kariera) — do trajektorii/awansu i do UI ---
    const perYear: SeasonScore[] = [...p.seasons]
      .sort((a, b) => a.year - b.year)
      .map((s) => ({
        year: s.year,
        league: s.league,
        yearZ: composeYearZ(s, cohorts),
        games: s.games,
      }));

    // --- Cztery sygnały potencjału ---
    const base = composeYearZ(latestInLeague, cohorts) ?? ratingZ;

    const zPoints = perYear
      .filter((y) => y.yearZ !== null)
      .map((y) => ({ x: y.year, y: y.yearZ as number, w: sampleWeight(y.games) }));
    const trajectory = clamp(
      weightedSlope(zPoints),
      -TRAJECTORY_CLAMP,
      TRAJECTORY_CLAMP
    );

    const strengthPoints = perYear.map((y) => ({
      x: y.year,
      y: leagueStrength(y.league),
      w: sampleWeight(y.games),
    }));
    const ascension = weightedSlope(strengthPoints) * ASCENSION_SCALE;

    const dominance = base * (1 - strengthNorm(league));

    const age = p.birthdate
      ? careerLatestYear - p.birthdate.getUTCFullYear()
      : null;
    const ageF = age !== null ? ageFactor(age) : 0;

    const potentialZ =
      base +
      POTENTIAL_WEIGHTS.trajectory * trajectory +
      POTENTIAL_WEIGHTS.age * ageF +
      POTENTIAL_WEIGHTS.dominance * dominance +
      POTENTIAL_WEIGHTS.ascension * ascension;

    const cohortLatest = cohorts.get(
      cohortKey(role, league, latestInLeague.year)
    );
    const lowSample =
      gamesInLeague < MIN_SEASON_GAMES || (cohortLatest?.lowSample ?? true);

    out.push({
      overviewPage: p.overviewPage,
      league,
      role,
      age,
      games: gamesInLeague,
      rating: round1(to100(ratingZ)),
      ratingZ,
      tier: tierForZ(ratingZ),
      potential: round1(to100(potentialZ)),
      potentialZ,
      potentialLabel: labelForZ(potentialZ),
      lowSample,
      perYear,
    });
  }

  // Domyślne sortowanie: ocena malejąco, remis → wyższy potencjał.
  out.sort((a, b) => b.rating - a.rating || b.potential - a.potential);
  return out;
}

// --- Mapowania i wagi -------------------------------------------------------

function recencyWeight(year: number, latestYear: number): number {
  return RECENCY_DECAY ** (latestYear - year);
}

function sampleWeight(games: number): number {
  return Math.min(games, SAMPLE_CAP) / SAMPLE_CAP;
}

function sigmoid(x: number): number {
  return 1 / (1 + Math.exp(-x));
}

/** Composite-Z → skala 0..100 (czytelna dla coacha). */
export function to100(z: number): number {
  return 100 * sigmoid(LOGISTIC_K * z);
}

export function tierForZ(z: number): string {
  for (const t of TIER_THRESHOLDS) if (z >= t.minZ) return t.tier;
  return TIER_THRESHOLDS[TIER_THRESHOLDS.length - 1].tier;
}

export function labelForZ(z: number): string {
  for (const l of POTENTIAL_LABELS) if (z >= l.minZ) return l.label;
  return POTENTIAL_LABELS[POTENTIAL_LABELS.length - 1].label;
}

/** Wkład wieku z krzywej AGE_CURVE (interpolacja liniowa, brzegi płaskie). */
export function ageFactor(age: number): number {
  const c = AGE_CURVE;
  if (age <= c[0].age) return c[0].factor;
  if (age >= c[c.length - 1].age) return c[c.length - 1].factor;
  for (let i = 0; i < c.length - 1; i++) {
    const a = c[i];
    const b = c[i + 1];
    if (age >= a.age && age <= b.age) {
      const t = (age - a.age) / (b.age - a.age);
      return a.factor + t * (b.factor - a.factor);
    }
  }
  return 0;
}

/** Nachylenie ważonej regresji liniowej y~x (weighted least squares). */
export function weightedSlope(
  points: ReadonlyArray<{ x: number; y: number; w: number }>
): number {
  if (points.length < 2) return 0;
  let sw = 0;
  let swx = 0;
  let swy = 0;
  let swxx = 0;
  let swxy = 0;
  for (const p of points) {
    sw += p.w;
    swx += p.w * p.x;
    swy += p.w * p.y;
    swxx += p.w * p.x * p.x;
    swxy += p.w * p.x * p.y;
  }
  const denom = sw * swxx - swx * swx;
  if (denom === 0) return 0;
  return (sw * swxy - swx * swy) / denom;
}

function clamp(x: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, x));
}

function round1(x: number): number {
  return Math.round(x * 10) / 10;
}
