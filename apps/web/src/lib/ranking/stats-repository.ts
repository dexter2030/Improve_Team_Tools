/**
 * Player-stats repository — lp_player_stats (+ stan sync).
 * Wzorzec jak players/league-repository.ts: pełna podmiana per liga.
 */

import "server-only";

import { sql, eq, or, inArray } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  lpPlayerStats,
  lpPlayerStatsSync,
  lpPlayersAll,
  type LpPlayerStat,
  type NewLpPlayerStat,
} from "@/lib/db/schema";

/** Wszystkie sezony zsynchowane dla danej ligi (kohorta + gracze tej ligi). */
export async function listLeaguePlayerStats(
  league: string
): Promise<LpPlayerStat[]> {
  return db.select().from(lpPlayerStats).where(eq(lpPlayerStats.league, league));
}

/** Pełna kariera (wszystkie ligi/lata) dla zadanych graczy — do trajektorii i awansu. */
export async function listPlayerStatsFor(
  overviewPages: string[]
): Promise<LpPlayerStat[]> {
  if (overviewPages.length === 0) return [];
  return db
    .select()
    .from(lpPlayerStats)
    .where(inArray(lpPlayerStats.overviewPage, overviewPages));
}

/** Wszystkie zsynchowane sezony — do budowy kohort cross-league w rankingu. */
export async function listAllPlayerStats(): Promise<LpPlayerStat[]> {
  return db.select().from(lpPlayerStats);
}

/** Birthdate per gracz (z globalnej tabeli lp_players_all) — sygnał wieku. */
export async function birthdatesFor(
  overviewPages: string[]
): Promise<Map<string, Date | null>> {
  const out = new Map<string, Date | null>();
  if (overviewPages.length === 0) return out;
  const rows = await db
    .select({
      overviewPage: lpPlayersAll.overviewPage,
      birthdate: lpPlayersAll.birthdate,
    })
    .from(lpPlayersAll)
    .where(inArray(lpPlayersAll.overviewPage, overviewPages));
  for (const r of rows) out.set(r.overviewPage, r.birthdate);
  return out;
}

/**
 * Lata (sezony) obecne w statystykach — do selektora zakresu lat na widoku.
 * Z `league` zawęża do jednej ligi (opcje na stronie ligi), bez — całość
 * (strona narodowości). Malejąco: najnowszy rok najwyżej.
 */
export async function distinctStatYears(league?: string): Promise<number[]> {
  const where = league
    ? sql`WHERE ${lpPlayerStats.league} = ${league}`
    : sql``;
  const rows = await db.execute(sql`
    SELECT DISTINCT ${lpPlayerStats.year} AS year
    FROM ${lpPlayerStats}
    ${where}
    ORDER BY year DESC
  `);
  return rows.map((r) => r.year as number);
}

/**
 * OverviewPages graczy danej narodowości (z globalnej lp_players_all). Łapiemy
 * `Country` LUB `NationalityPrimary` — w Leaguepedii bywa wypełnione tylko jedno,
 * a oba niosą narodowość (Country = kraj pochodzenia, nie rezydencja gry).
 */
export async function pagesByNationality(country: string): Promise<string[]> {
  const rows = await db
    .select({ overviewPage: lpPlayersAll.overviewPage })
    .from(lpPlayersAll)
    .where(
      or(
        eq(lpPlayersAll.country, country),
        eq(lpPlayersAll.nationalityPrimary, country)
      )
    );
  return rows.map((r) => r.overviewPage);
}

/** Liczba zrankowanych graczy (distinct) per liga — do indeksu /ranking. */
export async function statsPlayerCounts(): Promise<Record<string, number>> {
  const rows = await db.execute(sql`
    SELECT ${lpPlayerStats.league} AS league,
           COUNT(DISTINCT ${lpPlayerStats.overviewPage})::int AS n
    FROM ${lpPlayerStats}
    GROUP BY ${lpPlayerStats.league}
  `);
  const out: Record<string, number> = {};
  for (const r of rows) out[r.league as string] = r.n as number;
  return out;
}

export async function getStatsSyncStates() {
  return db.select().from(lpPlayerStatsSync);
}

/**
 * Pełna podmiana sezonów danej ligi: DELETE where league + INSERT chunkami +
 * upsert stanu sync. Re-sync ciąga całe okno lat, więc czyścimy, by nie zostały
 * sieroty (np. gracze, którzy odeszli). Mirror upsertLeaguePlayers().
 *
 * Pusty wsad → no-op (NIE czyścimy), żeby nieudany/pusty fetch nie wymazał danych.
 */
export async function replaceLeagueStats(
  league: string,
  rows: NewLpPlayerStat[],
  lastGameDate: Date | null
): Promise<number> {
  if (rows.length === 0) return 0;

  await db.delete(lpPlayerStats).where(eq(lpPlayerStats.league, league));

  const CHUNK = 500;
  let total = 0;
  for (let i = 0; i < rows.length; i += CHUNK) {
    const chunk = rows.slice(i, i + CHUNK);
    await db.insert(lpPlayerStats).values(chunk);
    total += chunk.length;
  }

  const now = new Date();
  await db
    .insert(lpPlayerStatsSync)
    .values({ league, lastFetched: now, lastGameDate, count: total })
    .onConflictDoUpdate({
      target: lpPlayerStatsSync.league,
      set: { lastFetched: now, lastGameDate, count: total },
    });
  return total;
}
