/**
 * Singleton Drizzle client — lazy init.
 *
 * Top-level throw zabija Next.js build (collectPageData ładuje module
 * statycznie). Dlatego brak DATABASE_URL nie wybucha przy imporcie —
 * dopiero przy pierwszym query.
 *
 * `prepare: false` wymagane na Supavisor Transaction Pooler (port 6543)
 * i nieszkodliwe na direct connection / Session Pooler — zostawiamy
 * bezwarunkowo, żeby ten sam kod działał i lokalnie, i na Vercel.
 *
 * Singleton przez `globalThis` chroni przed wieloma instancjami podczas
 * hot reloadu Next.js w dev mode (każdy reload tworzyłby nowe
 * połączenie, wyczerpując pulę).
 */

import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import postgres from "postgres";
import * as schema from "./schema";

declare global {
  // eslint-disable-next-line no-var
  var __pg__: ReturnType<typeof postgres> | undefined;
  // eslint-disable-next-line no-var
  var __db__: PostgresJsDatabase<typeof schema> | undefined;
}

function buildDb(): PostgresJsDatabase<typeof schema> {
  const connectionString = process.env.DATABASE_URL;
  if (!connectionString) {
    throw new Error(
      "DATABASE_URL is not set. " +
        "Lokalnie: dodaj do web/.env.local. " +
        "Na Vercel: Project Settings → Environment Variables."
    );
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
  return drizzle(client, { schema });
}

/**
 * Proxy: każdy property access wymusza lazy build dopiero przy
 * pierwszym użyciu. Build-time `next collect page data` nie ewaluuje
 * żadnych queries, tylko inicjalizuje proxy → bez throw.
 */
export const db = new Proxy({} as PostgresJsDatabase<typeof schema>, {
  get(_target, prop, receiver) {
    if (!globalThis.__db__) globalThis.__db__ = buildDb();
    return Reflect.get(globalThis.__db__, prop, receiver);
  },
});

export { schema };
