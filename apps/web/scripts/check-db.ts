import { loadEnvConfig } from "@next/env";
loadEnvConfig(process.cwd());

async function main() {
  // Dynamiczny import PO loadEnvConfig — inaczej db/index.ts czyta puste env
  // (ESM hoistuje importy przed top-level kod) i ląduje na noop localhost.
  const { sql } = await import("drizzle-orm");
  const { db } = await import("../src/lib/db/index");

  const tables = await db.execute(
    sql`select table_name from information_schema.tables where table_schema='public' and table_name like 'lp_%' order by table_name`
  );
  console.log("lp_ tables:", tables.map((r) => r.table_name));

  const cols = await db.execute(
    sql`select column_name from information_schema.columns where table_schema='public' and table_name='lp_players_all' and column_name='birthdate'`
  );
  console.log("lp_players_all.birthdate exists:", cols.length > 0);
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("FATAL:", e?.cause ?? e);
    process.exit(1);
  });
