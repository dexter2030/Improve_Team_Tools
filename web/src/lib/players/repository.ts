/**
 * Players repository — operacje na globalnej tabeli lp_players_all.
 */

import "server-only";

import { sql, eq } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  lpPlayersAll,
  lpPlayersSync,
  type LpPlayer,
  type NewLpPlayer,
} from "@/lib/db/schema";

export async function countPlayers(): Promise<number> {
  const r = await db.execute(sql`SELECT COUNT(*)::int AS n FROM ${lpPlayersAll}`);
  return (r[0]?.n as number) ?? 0;
}

export interface PlayerFilters {
  role?: string;
  country?: string;
  search?: string;
  hideRetired?: boolean;
  limit?: number;
}

export async function listPlayers(f: PlayerFilters = {}): Promise<LpPlayer[]> {
  const conditions: ReturnType<typeof sql>[] = [];
  if (f.role) conditions.push(sql`${lpPlayersAll.role} = ${f.role}`);
  if (f.country) conditions.push(sql`${lpPlayersAll.country} = ${f.country}`);
  if (f.hideRetired) conditions.push(sql`${lpPlayersAll.isRetired} = false`);
  if (f.search) {
    const term = `%${f.search}%`;
    conditions.push(
      sql`(${lpPlayersAll.id} ILIKE ${term} OR ${lpPlayersAll.team} ILIKE ${term} OR ${lpPlayersAll.overviewPage} ILIKE ${term})`
    );
  }

  const where =
    conditions.length === 0
      ? sql`TRUE`
      : sql.join(conditions, sql` AND `);

  return db
    .select()
    .from(lpPlayersAll)
    .where(where)
    .orderBy(lpPlayersAll.id)
    .limit(f.limit ?? 500);
}

export async function distinctRoles(): Promise<string[]> {
  const rows = await db.execute(sql`
    SELECT DISTINCT ${lpPlayersAll.role} AS role
    FROM ${lpPlayersAll}
    WHERE ${lpPlayersAll.role} IS NOT NULL AND ${lpPlayersAll.role} != ''
    ORDER BY role
  `);
  return rows.map((r) => r.role as string);
}

export async function distinctCountries(): Promise<string[]> {
  const rows = await db.execute(sql`
    SELECT DISTINCT ${lpPlayersAll.country} AS country
    FROM ${lpPlayersAll}
    WHERE ${lpPlayersAll.country} IS NOT NULL AND ${lpPlayersAll.country} != ''
    ORDER BY country
  `);
  return rows.map((r) => r.country as string);
}

export async function upsertPlayers(players: NewLpPlayer[]): Promise<number> {
  if (players.length === 0) return 0;
  // Postgres ON CONFLICT — w batchach 1000 żeby nie wybuchać payloadem.
  const CHUNK = 1000;
  let total = 0;
  for (let i = 0; i < players.length; i += CHUNK) {
    const chunk = players.slice(i, i + CHUNK);
    await db
      .insert(lpPlayersAll)
      .values(chunk)
      .onConflictDoUpdate({
        target: lpPlayersAll.overviewPage,
        set: {
          id: sql`excluded.id`,
          team: sql`excluded.team`,
          role: sql`excluded.role`,
          country: sql`excluded.country`,
          residency: sql`excluded.residency`,
          nationalityPrimary: sql`excluded.nationality_primary`,
          isRetired: sql`excluded.is_retired`,
          syncedAt: sql`excluded.synced_at`,
        },
      });
    total += chunk.length;
  }
  return total;
}

export async function getSyncState() {
  const [row] = await db
    .select()
    .from(lpPlayersSync)
    .where(eq(lpPlayersSync.id, 1))
    .limit(1);
  return row ?? null;
}

export async function setSyncState(input: {
  lastFetched: Date;
  totalCount: number;
}): Promise<void> {
  await db
    .insert(lpPlayersSync)
    .values({ id: 1, ...input })
    .onConflictDoUpdate({
      target: lpPlayersSync.id,
      set: { lastFetched: input.lastFetched, totalCount: input.totalCount },
    });
}
