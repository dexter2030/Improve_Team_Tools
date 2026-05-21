/**
 * Champion pool aggregation — port src/processing/champion_stats.py na TS.
 *
 * Grupuje per-game ScoreboardRow z Leaguepedia w podsumowanie per champion:
 * gry, wins/losses, średnie K/D/A/CS, KDA. Sortowane malejąco po grach,
 * potem alfabetycznie po nazwie championa.
 */

import type { ScoreboardRow } from "@/lib/leaguepedia";

export interface ChampionStat {
  champion: string;
  games: number;
  wins: number;
  losses: number;
  avgKills: number;
  avgDeaths: number;
  avgAssists: number;
  avgCs: number;
  kda: number;
  winRate: number; // 0..1
}

export function aggregateChampionStats(
  rows: readonly ScoreboardRow[]
): ChampionStat[] {
  const buckets = new Map<string, ScoreboardRow[]>();
  for (const r of rows) {
    if (!r.champion) continue;
    const arr = buckets.get(r.champion) ?? [];
    arr.push(r);
    buckets.set(r.champion, arr);
  }

  const out: ChampionStat[] = [];
  for (const [champion, champRows] of buckets) {
    const n = champRows.length;
    const wins = champRows.filter((r) => r.win).length;
    const avgK = sum(champRows.map((r) => r.kills)) / n;
    const avgD = sum(champRows.map((r) => r.deaths)) / n;
    const avgA = sum(champRows.map((r) => r.assists)) / n;
    const avgCs = sum(champRows.map((r) => r.cs)) / n;
    const kda = (avgK + avgA) / Math.max(avgD, 1);
    out.push({
      champion,
      games: n,
      wins,
      losses: n - wins,
      avgKills: round(avgK, 2),
      avgDeaths: round(avgD, 2),
      avgAssists: round(avgA, 2),
      avgCs: round(avgCs, 1),
      kda: round(kda, 2),
      winRate: n === 0 ? 0 : wins / n,
    });
  }

  // Malejąco po grach, potem alfabetycznie.
  out.sort((a, b) => b.games - a.games || a.champion.localeCompare(b.champion));
  return out;
}

function sum(xs: number[]): number {
  let s = 0;
  for (const x of xs) s += x;
  return s;
}

function round(x: number, decimals: number): number {
  const f = 10 ** decimals;
  return Math.round(x * f) / f;
}
