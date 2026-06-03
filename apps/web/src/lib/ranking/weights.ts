/**
 * Wszystkie stałe scoringu w JEDNYM miejscu — żeby kalibracja oceny/potencjału
 * była łatwa (styl `_TIER_BONUS` z hidden_gems/scoring.py).
 *
 * UWAGA metodologiczna: to przejrzysta HEURYSTYKA, nie predykcja. Wartości
 * dobrane tak, by skala 0..100 była czytelna dla coacha — do strojenia na
 * realnych danych.
 */

// --- Okno danych ------------------------------------------------------------

/** Ile ostatnich sezonów (lat) ciągniemy z Leaguepedii i bierzemy do oceny. */
export const RANKING_SINCE_YEARS = 5;

// --- Kohorta (normalizacja) -------------------------------------------------

/** Min. liczba graczy w kohorcie (rola×liga×rok), inaczej kohorta = low sample. */
export const MIN_COHORT_PLAYERS = 5;

/** Min. liczba gier w sezonie, by sezon nie był oznaczony jako low sample. */
export const MIN_SEASON_GAMES = 8;

/** Metryki wchodzące w composite Z (równe wagi w obrębie kohorty tej samej roli). */
export const SCORED_METRICS = [
  "kda",
  "csPerMin",
  "dpm",
  "kp",
  "goldShare",
] as const;
export type ScoredMetric = (typeof SCORED_METRICS)[number];

// --- Ocena ogólna (rating) --------------------------------------------------

/** Zanik wagi sezonu: waga_recency = DECAY^(najnowszyRok − rok). 0.6 ≈ half-life 1.36 roku. */
export const RECENCY_DECAY = 0.6;

/** Sufit „pełnej próby": sezon z >= tylu gier ma wagę próby = 1 (mniej → proporcjonalnie). */
export const SAMPLE_CAP = 25;

/** Stromość logistyki Z→0..100: score = 100·σ(k·z). k=0.9 → z=0:50, z≈2:~85. */
export const LOGISTIC_K = 0.9;

/** Progi composite-Z → tier (sprawdzane od góry). */
export const TIER_THRESHOLDS: ReadonlyArray<{ tier: string; minZ: number }> = [
  { tier: "S", minZ: 1.5 },
  { tier: "A", minZ: 0.7 },
  { tier: "B", minZ: -0.2 },
  { tier: "C", minZ: -1.0 },
  { tier: "D", minZ: Number.NEGATIVE_INFINITY },
];

// --- Potencjał (4 sygnały) --------------------------------------------------

/** Wagi sygnałów: potentialZ = baza + Σ waga·sygnał. */
export const POTENTIAL_WEIGHTS = {
  trajectory: 0.8, // trend formy rok-do-roku
  age: 0.7, // młodość = wyższy sufit
  dominance: 0.5, // przewaga nad ligą (tłumiona siłą ligi)
  ascension: 0.5, // awans do mocniejszych lig
} as const;

/** Przycięcie nachylenia trajektorii (Z/rok), żeby outliery nie dominowały. */
export const TRAJECTORY_CLAMP = 1.5;

/** Skala sygnału „awans": (zmiana siły ligi 0..100 na rok) → jednostki Z. */
export const ASCENSION_SCALE = 1 / 40; // +40 pkt siły / rok ≈ +1.0 Z

/**
 * Krzywa wieku → wkład (jednostki Z). Młodszy = wyższy; ~22 lata neutralne.
 * Interpolacja liniowa między punktami; poza zakresem — wartości brzegowe.
 */
export const AGE_CURVE: ReadonlyArray<{ age: number; factor: number }> = [
  { age: 16, factor: 1.0 },
  { age: 18, factor: 0.7 },
  { age: 20, factor: 0.35 },
  { age: 22, factor: 0.0 },
  { age: 24, factor: -0.25 },
  { age: 27, factor: -0.6 },
  { age: 30, factor: -0.9 },
];

/** Progi potential-Z → etykieta (sprawdzane od góry). */
export const POTENTIAL_LABELS: ReadonlyArray<{ label: string; minZ: number }> = [
  { label: "Wysoki sufit", minZ: 1.2 },
  { label: "Obiecujący", minZ: 0.4 },
  { label: "Solidny", minZ: -0.4 },
  { label: "Ograniczony", minZ: Number.NEGATIVE_INFINITY },
];
