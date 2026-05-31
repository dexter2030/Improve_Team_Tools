/**
 * Per-league players repository.
 */

import "server-only";

import { sql, eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  lpTournamentPlayers,
  lpTournamentPlayersSync,
  type LpTournamentPlayer,
  type NewLpTournamentPlayer,
} from "@/lib/db/schema";

export async function listLeaguePlayers(
  league: string,
  opts: {
    role?: string;
    search?: string;
  } = {}
): Promise<LpTournamentPlayer[]> {
  const conditions = [eq(lpTournamentPlayers.league, league)];
  if (opts.role) conditions.push(eq(lpTournamentPlayers.role, opts.role));
  if (opts.search) {
    const term = `%${opts.search}%`;
    conditions.push(
      sql`(${lpTournamentPlayers.id} ILIKE ${term} OR ${lpTournamentPlayers.team} ILIKE ${term} OR ${lpTournamentPlayers.overviewPage} ILIKE ${term})`
    );
  }
  return db
    .select()
    .from(lpTournamentPlayers)
    .where(and(...conditions))
    .orderBy(lpTournamentPlayers.team, lpTournamentPlayers.role);
}

export async function leagueCounts(): Promise<Record<string, number>> {
  const rows = await db.execute(sql`
    SELECT ${lpTournamentPlayers.league} AS league, COUNT(*)::int AS n
    FROM ${lpTournamentPlayers}
    GROUP BY ${lpTournamentPlayers.league}
  `);
  const out: Record<string, number> = {};
  for (const r of rows) out[r.league as string] = r.n as number;
  return out;
}

export async function getLeagueSyncStates() {
  return db.select().from(lpTournamentPlayersSync);
}

export async function upsertLeaguePlayers(
  league: string,
  players: NewLpTournamentPlayer[]
): Promise<number> {
  if (players.length === 0) return 0;
  // Wymiana całej ligi — prościej niż diff (rostery zmieniają się przy
  // transferach, dropowanie nieaktualnych jest pożądane).
  await db
    .delete(lpTournamentPlayers)
    .where(eq(lpTournamentPlayers.league, league));

  const CHUNK = 500;
  let total = 0;
  for (let i = 0; i < players.length; i += CHUNK) {
    const chunk = players.slice(i, i + CHUNK);
    await db.insert(lpTournamentPlayers).values(chunk);
    total += chunk.length;
  }
  await db
    .insert(lpTournamentPlayersSync)
    .values({ league, lastFetched: new Date(), count: total })
    .onConflictDoUpdate({
      target: lpTournamentPlayersSync.league,
      set: { lastFetched: new Date(), count: total },
    });
  return total;
}

export async function distinctRolesInLeague(league: string): Promise<string[]> {
  const rows = await db.execute(sql`
    SELECT DISTINCT ${lpTournamentPlayers.role} AS role
    FROM ${lpTournamentPlayers}
    WHERE ${lpTournamentPlayers.league} = ${league}
      AND ${lpTournamentPlayers.role} IS NOT NULL
      AND ${lpTournamentPlayers.role} != ''
    ORDER BY role
  `);
  return rows.map((r) => r.role as string);
}
