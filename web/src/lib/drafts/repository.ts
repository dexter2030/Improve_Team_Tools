/**
 * Drafts repository — operacje na drafts + league_sync.
 */

import "server-only";

import { sql, eq, inArray } from "drizzle-orm";
import { db } from "@/lib/db";
import { drafts, leagueSync, type Draft } from "@/lib/db/schema";
import type { RawDraft } from "@/lib/leaguepedia/drafts";

// --- Drafts ----------------------------------------------------------------

export async function getAllDrafts(): Promise<Draft[]> {
  return db.select().from(drafts).orderBy(sql`${drafts.gameDate} DESC`);
}

export async function getDraftsByLeagues(leagues: string[]): Promise<Draft[]> {
  if (leagues.length === 0) return getAllDrafts();
  // SQL LIKE per league — substring match jest po polach po stronie JS w
  // filterByLeagues(), tutaj robimy tylko wstępne zawężenie tabelarne.
  const conditions = leagues.map(
    (l) => sql`${drafts.league} ILIKE ${`%${l}%`}`
  );
  return db
    .select()
    .from(drafts)
    .where(sql.join(conditions, sql` OR `))
    .orderBy(sql`${drafts.gameDate} DESC`);
}

export async function countAllDrafts(): Promise<number> {
  const result = await db.execute(sql`SELECT COUNT(*)::int AS n FROM ${drafts}`);
  return (result[0]?.n as number) ?? 0;
}

/**
 * Distinct patches w bazie, posortowane MALEJĄCO numerycznie (najnowsze pierwsze).
 * SQL ORDER BY na string daje leksykograficznie ("9.6" > "9.16"); sortujemy
 * po stronie kodu po sortPatchesDesc() która rozumie format Riot patchy.
 */
export async function distinctPatches(): Promise<string[]> {
  const rows = await db.execute(sql`
    SELECT DISTINCT ${drafts.patch} AS patch
    FROM ${drafts}
    WHERE ${drafts.patch} IS NOT NULL
  `);
  const list = rows.map((r) => r.patch as string);
  const { sortPatchesDesc } = await import("./analyzer");
  return sortPatchesDesc(list);
}

/**
 * Bulk upsert draftów w chunkach po CHUNK_SIZE. Idempotentne — ten sam
 * matchId nadpisuje stary wiersz.
 *
 * Chunking konieczny dla dużych lig (LPL/LCK mają 5k-10k+ historycznych
 * gier). Jeden gigantyczny INSERT z 10k×17 placeholderów (postgres-js
 * z prepare:false) wybijał "Maximum call stack size exceeded" przy
 * serializacji parametrów.
 */
const CHUNK_SIZE = 500;

export async function upsertDrafts(rows: RawDraft[]): Promise<number> {
  if (rows.length === 0) return 0;
  let total = 0;
  for (let i = 0; i < rows.length; i += CHUNK_SIZE) {
    const chunk = rows.slice(i, i + CHUNK_SIZE);
    await db
      .insert(drafts)
      .values(
        chunk.map((r) => ({
          matchId: r.matchId,
          patch: r.patch,
          league: r.league,
          gameDate: r.gameDate,
          blueTeam: r.blueTeam,
          redTeam: r.redTeam,
          blueBans: r.blueBans,
          redBans: r.redBans,
          b1Pick: r.b1Pick,
          r1Pick: r.r1Pick,
          r2Pick: r.r2Pick,
          b2Pick: r.b2Pick,
          b3Pick: r.b3Pick,
          r3Pick: r.r3Pick,
          b4Pick: r.b4Pick,
          b5Pick: r.b5Pick,
          r4Pick: r.r4Pick,
          r5Pick: r.r5Pick,
          firstPickSide: r.firstPickSide,
          winner: r.winner,
        }))
      )
      .onConflictDoUpdate({
        target: drafts.matchId,
        set: {
          patch: sql`excluded.patch`,
          league: sql`excluded.league`,
          gameDate: sql`excluded.game_date`,
          blueTeam: sql`excluded.blue_team`,
          redTeam: sql`excluded.red_team`,
          blueBans: sql`excluded.blue_bans`,
          redBans: sql`excluded.red_bans`,
          b1Pick: sql`excluded.b1_pick`,
          r1Pick: sql`excluded.r1_pick`,
          r2Pick: sql`excluded.r2_pick`,
          b2Pick: sql`excluded.b2_pick`,
          b3Pick: sql`excluded.b3_pick`,
          r3Pick: sql`excluded.r3_pick`,
          b4Pick: sql`excluded.b4_pick`,
          b5Pick: sql`excluded.b5_pick`,
          r4Pick: sql`excluded.r4_pick`,
          r5Pick: sql`excluded.r5_pick`,
          firstPickSide: sql`excluded.first_pick_side`,
          winner: sql`excluded.winner`,
        },
      });
    total += chunk.length;
  }
  return total;
}

// --- League sync state -----------------------------------------------------

export async function getLeagueSyncAll() {
  return db.select().from(leagueSync);
}

export async function getLeagueSync(league: string) {
  const [row] = await db
    .select()
    .from(leagueSync)
    .where(eq(leagueSync.league, league))
    .limit(1);
  return row ?? null;
}

export async function upsertLeagueSync(input: {
  league: string;
  lastFetched?: Date | null;
  lastGameDate?: Date | null;
  remoteTotal?: number | null;
  remoteChecked?: Date | null;
}): Promise<void> {
  await db
    .insert(leagueSync)
    .values({
      league: input.league,
      lastFetched: input.lastFetched ?? null,
      lastGameDate: input.lastGameDate ?? null,
      remoteTotal: input.remoteTotal ?? null,
      remoteChecked: input.remoteChecked ?? null,
    })
    .onConflictDoUpdate({
      target: leagueSync.league,
      set: {
        ...(input.lastFetched !== undefined && { lastFetched: input.lastFetched }),
        ...(input.lastGameDate !== undefined && { lastGameDate: input.lastGameDate }),
        ...(input.remoteTotal !== undefined && { remoteTotal: input.remoteTotal }),
        ...(input.remoteChecked !== undefined && { remoteChecked: input.remoteChecked }),
      },
    });
}

/** Drafts count per league (key = league name). */
export async function draftCountsByLeague(): Promise<Record<string, number>> {
  const rows = await db.execute(sql`
    SELECT ${drafts.league} AS league, COUNT(*)::int AS n
    FROM ${drafts}
    GROUP BY ${drafts.league}
  `);
  const out: Record<string, number> = {};
  for (const r of rows) out[r.league as string] = r.n as number;
  return out;
}
