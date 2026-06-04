/**
 * GET /api/health
 *
 * Sanity check: czy Next.js → Drizzle → Supabase działa end-to-end.
 * Zwraca rozmiary tabel rdzennych. Jeśli DB nie odpowiada, status 500.
 *
 * Dodatkowo sonduje schemat RANKINGU (lp_player_stats + kolumny split): strony
 * /ranking crashują, gdy migracje 0007/0008 nie są przeparte na bazie tego
 * deploymentu, a sama łączność (tabele rdzenne) bywa wtedy zielona. `degraded`
 * + `ranking.hint` czynią ten przypadek widocznym z przycisku „Check /api/health".
 */

import { sql } from "drizzle-orm";
import { db, schema } from "@/lib/db";

interface RankingProbe {
  ready: boolean; // tabela + kolumny split obecne (brak crasha tras rankingu)
  table: boolean;
  splitColumns: boolean;
  rows: number;
  hint?: string;
  error?: string;
}

/** Read-only: stan schematu rankingu. Łapie własne błędy, by nie wywalić health. */
async function probeRanking(): Promise<RankingProbe> {
  try {
    const reg = await db.execute(
      sql`SELECT to_regclass('public.lp_player_stats') AS t`
    );
    const hasTable = ((reg[0]?.t as string | null) ?? null) !== null;
    if (!hasTable) {
      return {
        ready: false,
        table: false,
        splitColumns: false,
        rows: 0,
        hint: "Brak tabel rankingu — uruchom: npx drizzle-kit migrate",
      };
    }

    const cols = await db.execute(sql`
      SELECT count(*) FILTER (
        WHERE column_name IN ('split', 'split_order')
      )::int AS split_cols
      FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = 'lp_player_stats'`);
    const splitColumns = ((cols[0]?.split_cols as number) ?? 0) >= 2;

    const cnt = await db.execute(sql`SELECT count(*)::int AS n FROM lp_player_stats`);
    const rows = (cnt[0]?.n as number) ?? 0;

    const ready = hasTable && splitColumns;
    const hint = !splitColumns
      ? "Brak kolumn split/split_order — uruchom: npx drizzle-kit migrate (0008)"
      : rows === 0
        ? "Schemat OK, brak danych — uruchom: npx tsx scripts/load-ranking.ts --force"
        : undefined;

    return { ready, table: true, splitColumns, rows, ...(hint ? { hint } : {}) };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ready: false,
      table: false,
      splitColumns: false,
      rows: 0,
      error: message,
      hint: "Sonda rankingu padła — sprawdź migracje (drizzle-kit migrate)",
    };
  }
}

export async function GET() {
  try {
    const [profiles, soloq, proplay, cache, ranking] = await Promise.all([
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.scoutingProfiles}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.soloqAccounts}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.proplayIdentities}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.apiCache}`),
      probeRanking(),
    ]);

    return Response.json({
      ok: true,
      database: "connected",
      degraded: !ranking.ready,
      tables: {
        scouting_profiles: (profiles[0]?.n as number) ?? 0,
        soloq_accounts: (soloq[0]?.n as number) ?? 0,
        proplay_identities: (proplay[0]?.n as number) ?? 0,
        api_cache: (cache[0]?.n as number) ?? 0,
      },
      ranking,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
