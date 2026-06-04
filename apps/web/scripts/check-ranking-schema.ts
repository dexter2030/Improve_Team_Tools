/**
 * Read-only diagnostyka: którą migrację rankingu ma faktycznie baza z
 * DATABASE_URL (z .env.local). Nic nie modyfikuje. Odpowiada na pytanie
 * „czy deployment crashuje przez brak migracji 0007/0008".
 *
 * Użycie (z apps/web):
 *   npx tsx scripts/check-ranking-schema.ts
 *
 * Wynik: obecność tabeli lp_player_stats, kolumn split/split_order, liczba
 * wierszy i wywnioskowany poziom migracji.
 */
import { loadEnvConfig } from "@next/env";
loadEnvConfig(process.cwd());
import postgres from "postgres";

async function main() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    console.log(JSON.stringify({ error: "Brak DATABASE_URL w env" }));
    process.exit(1);
  }
  let host = "(unparseable)";
  try {
    host = new URL(url).host;
  } catch {
    /* ignore */
  }

  const sql = postgres(url, { prepare: false, max: 1 });
  try {
    const tbl = await sql`SELECT to_regclass('public.lp_player_stats') AS t`;
    const hasTable = tbl[0].t !== null;

    let hasSplit = false;
    let hasSplitOrder = false;
    let rowCount = -1;
    if (hasTable) {
      const cols = await sql`
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'lp_player_stats'`;
      const names = new Set(cols.map((c) => c.column_name as string));
      hasSplit = names.has("split");
      hasSplitOrder = names.has("split_order");
      const cnt = await sql`SELECT count(*)::int AS n FROM lp_player_stats`;
      rowCount = cnt[0].n as number;
    }

    const inferred = !hasTable
      ? "<= 0006 (brak tabeli lp_player_stats — crash także /ranking)"
      : !hasSplit || !hasSplitOrder
        ? "0007 (tabela jest, brak split/split_order — crash /ranking/[liga] i /nationality)"
        : rowCount === 0
          ? ">= 0008 (schemat OK, brak danych — odpal load-ranking.ts --force)"
          : ">= 0008 (schemat OK, dane są — ranking powinien działać)";

    console.log(
      JSON.stringify(
        {
          host,
          lp_player_stats_table: hasTable,
          split_column: hasSplit,
          split_order_column: hasSplitOrder,
          row_count: rowCount,
          inferred_migration_level: inferred,
        },
        null,
        2
      )
    );
  } finally {
    await sql.end({ timeout: 5 });
  }
}

main().catch((e) => {
  console.error("ERR", (e as { message?: string })?.message ?? e);
  process.exit(1);
});
