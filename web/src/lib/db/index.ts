/**
 * Singleton Drizzle client — eager construction, lazy connection.
 *
 * postgres-js nie nawiązuje connection przy `postgres(url, ...)` — dopiero
 * przy pierwszym query. Możemy więc bezpiecznie skonstruować klienta z
 * placeholder URL przy buildzie (gdy env nie istnieje), a Drizzle owinąć
 * na nim. Runtime query z prawdziwym DATABASE_URL załatwia connection
 * przy pierwszym requeście.
 *
 * Wcześniejszy lazy Proxy gubił `this` w chained calls Drizzle
 * (db.select().from()) — eager init unika tego całkowicie.
 *
 * `prepare: false` wymagane na Supavisor Transaction Pooler i nieszkodliwe
 * gdzie indziej.
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

const PLACEHOLDER_URL = "postgres://noop:noop@127.0.0.1:5432/noop";

declare global {
  // eslint-disable-next-line no-var
  var __pg__: ReturnType<typeof postgres> | undefined;
}

function buildClient() {
  const url = process.env.DATABASE_URL ?? PLACEHOLDER_URL;
  if (url === PLACEHOLDER_URL && process.env.NEXT_PHASE !== "phase-production-build") {
    console.warn(
      "[db] DATABASE_URL not set — używam placeholder, queries padną na runtime."
    );
  }
  return postgres(url, { prepare: false, max: 10 });
}

const client = globalThis.__pg__ ?? buildClient();
if (process.env.NODE_ENV !== "production") globalThis.__pg__ = client;

export const db = drizzle(client, { schema });
export { schema };
