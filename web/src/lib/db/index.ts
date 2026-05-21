/**
 * Singleton Drizzle client.
 *
 * Vercel serverless reuse function instancji (warm starts) — globalThis
 * persistuje między requestami w tej samej instancji. Bez cache każdy
 * cold start tworzyłby N connectionów do Supavisor poolera (Supabase free
 * tier ma per-user limit 15), wyczerpując pool po kilkunastu requestach.
 *
 * `prepare: false` wymagane dla Supavisor Transaction Pool (port 6543);
 * Session Pool (port 5432) też to wspiera, więc zostawiamy bezwarunkowo.
 *
 * `max: 1` na połączenie per-instance — Vercel autoskaluje funkcje
 * horyzontalnie, więc lepiej wiele instancji × 1 connection niż
 * jedna instancja × wiele connectionów (które i tak Supabase odetnie).
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

declare global {
  // eslint-disable-next-line no-var
  var __pg__: ReturnType<typeof postgres> | undefined;
}

function buildClient() {
  const url = process.env.DATABASE_URL;
  if (!url) {
    // Placeholder żeby Next.js build (który ewaluuje moduł przy
    // analizie pages) nie wybuchał. Runtime query padnie z connection
    // refused — to OK, znaczy że brak env w Vercel Project Settings.
    return postgres("postgres://noop:noop@127.0.0.1:5432/noop", {
      prepare: false,
      max: 1,
    });
  }
  return postgres(url, { prepare: false, max: 1 });
}

const client = globalThis.__pg__ ?? buildClient();
globalThis.__pg__ = client; // zawsze cache — nawet w production

export const db = drizzle(client, { schema });
export { schema };
