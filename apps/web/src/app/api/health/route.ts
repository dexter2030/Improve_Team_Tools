/**
 * GET /api/health
 *
 * Sanity check: czy Next.js → Drizzle → Supabase działa end-to-end.
 * Zwraca rozmiary tabel rdzennych. Jeśli DB nie odpowiada, status 500.
 */

import { sql } from "drizzle-orm";
import { db, schema } from "@/lib/db";

export async function GET() {
  try {
    const [profiles, soloq, proplay, cache] = await Promise.all([
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.scoutingProfiles}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.soloqAccounts}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.proplayIdentities}`),
      db.execute(sql`SELECT count(*)::int AS n FROM ${schema.apiCache}`),
    ]);

    return Response.json({
      ok: true,
      database: "connected",
      tables: {
        scouting_profiles: (profiles[0]?.n as number) ?? 0,
        soloq_accounts: (soloq[0]?.n as number) ?? 0,
        proplay_identities: (proplay[0]?.n as number) ?? 0,
        api_cache: (cache[0]?.n as number) ?? 0,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
