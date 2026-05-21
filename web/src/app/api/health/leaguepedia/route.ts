/**
 * GET /api/health/leaguepedia
 *
 * Sanity check Cargo API + LeaguepediaClient + Supabase cache TTL flow.
 * Szuka znanego gracza ("Faker") i raportuje liczbę dopasowań + przykład.
 */

import { getLeaguepediaClient } from "@/lib/leaguepedia";

export async function GET() {
  try {
    const client = getLeaguepediaClient();
    const players = await client.searchPlayersById("Faker");

    return Response.json({
      ok: true,
      handle: "Faker",
      matches: players.length,
      sample: players.slice(0, 3),
      authStatus: client.authStatus(),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const stack = err instanceof Error ? err.stack?.split("\n").slice(0, 3) : undefined;
    return Response.json({ ok: false, error: message, stack }, { status: 500 });
  }
}
