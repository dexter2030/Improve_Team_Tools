import { loadEnvConfig } from "@next/env";
loadEnvConfig(process.cwd());

async function main() {
  const { sql } = await import("drizzle-orm");
  const { db } = await import("../src/lib/db/index");

  const per = await db.execute(
    sql`select league, count(*)::int as rows, count(distinct overview_page)::int as players,
        count(distinct split)::int as splits, min(year)::int as y0, max(year)::int as y1
        from lp_player_stats group by league order by rows desc`
  );
  console.log("=== lp_player_stats per liga ===");
  console.table(per);

  const tot = await db.execute(
    sql`select count(*)::int as rows, count(distinct overview_page)::int as players,
        count(distinct split)::int as splits from lp_player_stats`
  );
  console.log("TOTAL:", tot[0]);

  const bd = await db.execute(
    sql`select count(*)::int as with_birthdate from lp_players_all where birthdate is not null`
  );
  console.log("gracze z birthdate:", bd[0]?.with_birthdate);

  console.log("=== próbka: LEC 2025, top 5 wg KDA ===");
  const sample = await db.execute(
    sql`select overview_page, split, role, games,
        round(kda::numeric,2) as kda, round(cs_per_min::numeric,2) as cspm,
        round(dpm::numeric,0) as dpm, round((winrate*100)::numeric,0) as wr
        from lp_player_stats where league='LEC' and year=2025
        order by kda desc nulls last limit 5`
  );
  console.table(sample);
}

main()
  .then(() => process.exit(0))
  .catch((e) => {
    console.error("FATAL:", (e as { cause?: unknown })?.cause ?? e);
    process.exit(1);
  });
