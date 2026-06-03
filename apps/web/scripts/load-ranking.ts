/**
 * Jednorazowy loader danych rankingu do bazy (Supabase) — z pacingiem pod
 * rate-limit Leaguepedia Cargo.
 *
 * Pobiera ScoreboardPlayers per liga (okno 5 lat) → agreguje per (gracz, rok,
 * split) → zapisuje do lp_player_stats. Następnie CELOWANO uzupełnia birthdate w
 * lp_players_all (tylko dla wczytanych graczy). Importy względne, bez modułów
 * "server-only"; `db` ładowany dynamicznie PO loadEnvConfig.
 *
 * Użycie (z apps/web):
 *   npx tsx scripts/load-ranking.ts                 # LEC + ERL D1, pomija już wczytane, + birthdates
 *   npx tsx scripts/load-ranking.ts --force         # wczytaj wszystkie od nowa
 *   npx tsx scripts/load-ranking.ts LFL             # tylko LFL
 *   npx tsx scripts/load-ranking.ts --no-birthdates # pomiń birthdates
 */

import { loadEnvConfig } from "@next/env";
loadEnvConfig(process.cwd());

import { sql, eq, inArray } from "drizzle-orm";
import {
  lpPlayerStats,
  lpPlayerStatsSync,
  lpPlayersAll,
} from "../src/lib/db/schema";
import { fetchScoreboardPlayers } from "../src/lib/leaguepedia/scoreboard";
import { aggregatePlayerSplits } from "../src/lib/ranking/aggregate";
import { LEAGUE_GROUPS } from "../src/lib/leaguepedia/leagues";
import { cargoQuery, cargoEscape, toStr } from "../src/lib/leaguepedia/cargo";

let db: Awaited<typeof import("../src/lib/db/index")>["db"];

const SINCE_YEARS = 5;
const sinceYear = new Date().getUTCFullYear() - (SINCE_YEARS - 1);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const isRateLimited = (e: unknown) =>
  /ratelimit|rate limit|429/i.test(String((e as { message?: string })?.message ?? e));

async function loadLeague(league: string) {
  // Retry całej ligi na rate-limit (cargo robi krótkie retry; tu dłuższe).
  let lastErr: unknown;
  for (let attempt = 0; attempt < 4; attempt++) {
    if (attempt > 0) {
      console.log(`      ...rate-limit, czekam 60s przed ponowieniem ${league}`);
      await sleep(60000);
    }
    try {
      const rows = await fetchScoreboardPlayers(league, { sinceYear });
      const aggs = aggregatePlayerSplits(rows);
      await db.delete(lpPlayerStats).where(eq(lpPlayerStats.league, league));
      const now = new Date();
      const CHUNK = 500;
      let saved = 0;
      for (let i = 0; i < aggs.length; i += CHUNK) {
        const chunk = aggs.slice(i, i + CHUNK).map((a) => ({ ...a, syncedAt: now }));
        if (chunk.length) await db.insert(lpPlayerStats).values(chunk);
        saved += chunk.length;
      }
      await db
        .insert(lpPlayerStatsSync)
        .values({ league, lastFetched: now, lastGameDate: null, count: saved })
        .onConflictDoUpdate({
          target: lpPlayerStatsSync.league,
          set: { lastFetched: now, lastGameDate: null, count: saved },
        });
      return { league, fetched: rows.length, saved };
    } catch (e) {
      lastErr = e;
      if (!isRateLimited(e)) throw e;
    }
  }
  throw lastErr;
}

function parseBirthdate(v: unknown): Date | null {
  const s = toStr(v).trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(`${s}T00:00:00Z`);
  return Number.isFinite(d.getTime()) ? d : null;
}

/** Birthdate tylko dla wczytanych graczy — chunkami z pacingiem (oszczędza limit). */
async function loadBirthdatesTargeted() {
  const rows = await db
    .selectDistinct({ op: lpPlayerStats.overviewPage })
    .from(lpPlayerStats);
  const pages = rows.map((r) => r.op);
  console.log(`[load] birthdates dla ${pages.length} graczy (celowane)...`);
  const CH = 80;
  let updated = 0;
  for (let i = 0; i < pages.length; i += CH) {
    const chunk = pages.slice(i, i + CH);
    const where = chunk
      .map((p) => `Players.OverviewPage='${cargoEscape(p)}'`)
      .join(" OR ");
    let cargoRows: Array<Record<string, unknown>> = [];
    for (let attempt = 0; attempt < 4; attempt++) {
      if (attempt > 0) await sleep(60000);
      try {
        cargoRows = await cargoQuery({
          tables: "Players",
          fields: "Players.OverviewPage=op,Players.Birthdate=bd",
          where,
          limit: 500,
        });
        break;
      } catch (e) {
        if (!isRateLimited(e) || attempt === 3) throw e;
      }
    }
    for (const r of cargoRows) {
      const bd = parseBirthdate(r.bd);
      if (!bd) continue;
      await db
        .update(lpPlayersAll)
        .set({ birthdate: bd })
        .where(eq(lpPlayersAll.overviewPage, toStr(r.op)));
      updated++;
    }
    await sleep(6000); // pacing między chunkami
  }
  return updated;
}

async function alreadyLoaded(): Promise<Set<string>> {
  const rows = await db.select().from(lpPlayerStatsSync);
  return new Set(rows.filter((r) => (r.count ?? 0) > 0).map((r) => r.league));
}

async function main() {
  ({ db } = await import("../src/lib/db/index"));

  const args = process.argv.slice(2);
  const argLeagues = args.filter((a) => !a.startsWith("--"));
  const force = args.includes("--force");
  const fullMode = argLeagues.length === 0;
  const wanted = fullMode ? ["LEC", ...LEAGUE_GROUPS.erlD1] : argLeagues;
  const doBirthdates = !args.includes("--no-birthdates");

  const loaded = force ? new Set<string>() : await alreadyLoaded();
  const leagues = wanted.filter((l) => !loaded.has(l));
  if (loaded.size)
    console.log(`[skip] już wczytane: ${[...loaded].join(", ")}`);
  console.log(
    `[load] okno od ${sinceYear}; do zrobienia (${leagues.length}): ${leagues.join(", ") || "—"}`
  );

  const results: Array<Record<string, unknown>> = [];
  for (let i = 0; i < leagues.length; i++) {
    const lg = leagues[i];
    try {
      const r = await loadLeague(lg);
      console.log(`[ok]  ${r.league}: ${r.saved} splitów (z ${r.fetched} gier)`);
      results.push(r);
    } catch (e) {
      const msg = (e as { message?: string })?.message ?? e;
      console.error(`[err] ${lg}: ${msg}`);
      results.push({ league: lg, error: String(msg) });
    }
    if (i < leagues.length - 1) await sleep(20000); // pacing między ligami
  }

  if (doBirthdates) {
    try {
      const n = await loadBirthdatesTargeted();
      console.log(`[ok]  birthdates: zaktualizowano ${n} graczy`);
    } catch (e) {
      console.error(`[err] birthdates: ${(e as { message?: string })?.message ?? e}`);
    }
  }

  console.log(`[done] ${JSON.stringify(results)}`);
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("FATAL:", (e as { cause?: unknown })?.cause ?? e);
    process.exit(1);
  });
