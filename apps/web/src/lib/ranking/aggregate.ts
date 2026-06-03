/**
 * Agregacja surowych wierszy meczowych (ScoreboardPlayers) w SPLITY
 * gracza: jeden rekord per (gracz, rok, liga, split). Port
 * hidden_gems/leaguepedia.py::aggregate_player_stats, rozbity do grana splitu.
 *
 * Wszystkie wskaźniki to średnia z wartości PER MECZ (nie z totali) — żeby
 * jeden mecz koksowy nie dominował średniej. Metryka = null, gdy brak danych
 * (np. brak długości gry → brak CS/min; brak team_gold → brak gold_share).
 */

import type { ScoreboardPlayerRow } from "@/lib/leaguepedia/types";

export interface PlayerSplitAggregate {
  overviewPage: string;
  year: number;
  league: string;
  split: string;
  splitOrder: number; // rok + ułamek splitu — oś x trajektorii / sortowanie
  role: string | null;
  games: number;
  wins: number;
  winrate: number; // 0..1
  kda: number | null;
  csPerMin: number | null;
  dpm: number | null;
  kp: number | null;
  goldShare: number | null;
}

/** Jednoznaczny klucz (gracz, rok, liga, split) — JSON, by uniknąć kolizji separatorów. */
function bucketKey(r: ScoreboardPlayerRow): string {
  return JSON.stringify([r.link, r.year, r.league, r.split]);
}

export function aggregatePlayerSplits(
  rows: readonly ScoreboardPlayerRow[]
): PlayerSplitAggregate[] {
  const buckets = new Map<string, ScoreboardPlayerRow[]>();
  for (const r of rows) {
    const key = bucketKey(r);
    const arr = buckets.get(key);
    if (arr) arr.push(r);
    else buckets.set(key, [r]);
  }

  const out: PlayerSplitAggregate[] = [];
  for (const group of buckets.values()) out.push(aggregateGroup(group));
  return out;
}

function aggregateGroup(rows: ScoreboardPlayerRow[]): PlayerSplitAggregate {
  const first = rows[0];
  const games = rows.length;
  const wins = rows.filter((r) => r.win).length;
  // splitOrder jest stały w obrębie bucketu (rok+ułamek z SplitNumber/etykiety);
  // min jako zabezpieczenie, gdyby fallback po miesiącu dał drobny rozjazd.
  const splitOrder = rows.reduce((m, r) => Math.min(m, r.splitOrder), first.splitOrder);

  const perKda: number[] = [];
  const perCspm: number[] = [];
  const perDpm: number[] = [];
  const perKp: number[] = [];
  const perGoldShare: number[] = [];

  for (const r of rows) {
    // KDA z deaths=0 → „perfekcyjne": dzielimy przez max(deaths, 1).
    perKda.push((r.kills + r.assists) / Math.max(r.deaths, 1));
    if (r.gameLength && r.gameLength > 0) {
      perCspm.push(r.cs / r.gameLength);
      perDpm.push(r.damage / r.gameLength);
    }
    if (r.teamKills > 0) perKp.push((r.kills + r.assists) / r.teamKills);
    if (r.teamGold > 0) perGoldShare.push(r.gold / r.teamGold);
  }

  return {
    overviewPage: first.link,
    year: first.year,
    league: first.league,
    split: first.split,
    splitOrder,
    role: dominantRole(rows),
    games,
    wins,
    winrate: wins / games,
    kda: avg(perKda),
    csPerMin: avg(perCspm),
    dpm: avg(perDpm),
    kp: avg(perKp),
    goldShare: avg(perGoldShare),
  };
}

function avg(xs: number[]): number | null {
  if (xs.length === 0) return null;
  let s = 0;
  for (const x of xs) s += x;
  return s / xs.length;
}

/** Najczęstsza rola w sezonie (gracz może zmieniać rolę — bierzemy dominującą). */
function dominantRole(rows: ScoreboardPlayerRow[]): string | null {
  const counts = new Map<string, number>();
  for (const r of rows) {
    if (!r.role) continue;
    counts.set(r.role, (counts.get(r.role) ?? 0) + 1);
  }
  let best: string | null = null;
  let bestN = 0;
  for (const [role, n] of counts) {
    if (n > bestN) {
      best = role;
      bestN = n;
    }
  }
  return best;
}
