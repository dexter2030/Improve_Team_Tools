/**
 * Singleton Drizzle client.
 *
 * Używamy `postgres` (postgres-js). `prepare: false` jest wymagane na
 * Supabase Transaction Pooler (port 6543) i nieszkodliwe na direct
 * connection (5432) — zostawiamy bezwarunkowo, żeby ten sam kod
 * działał i lokalnie, i na Vercel.
 *
 * Singleton przez `globalThis` chroni przed wieloma instancjami
 * podczas hot reloadu Next.js w dev mode (każdy reload tworzyłby
 * nowe połączenie, wyczerpując pulę).
 */

import { drizzle } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

declare global {
  // eslint-disable-next-line no-var
  var __pg__: ReturnType<typeof postgres> | undefined;
}

const connectionString = process.env.DATABASE_URL;
if (!connectionString) {
  throw new Error("DATABASE_URL is not set — check web/.env.local");
}

const client =
  globalThis.__pg__ ??
  postgres(connectionString, {
    prepare: false,
    max: 10,
  });

if (process.env.NODE_ENV !== "production") {
  globalThis.__pg__ = client;
}

export const db = drizzle(client, { schema });
export { schema };
