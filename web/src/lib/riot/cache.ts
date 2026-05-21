/**
 * Cache adapter pod Supabase `api_cache` table.
 *
 * Strukturalny protokół (interface) — RiotClient zależy od `CacheStore`,
 * nie od konkretnej implementacji. Tu jest tylko ten jeden adapter, bo
 * apka ma jedną bazę, ale Protocol zostaje na wypadek testów (in-memory)
 * lub przyszłej migracji.
 *
 * Lazy eviction: wygasłe wpisy usuwamy przy odczycie, nie przez cron.
 */

import { sql } from "drizzle-orm";
import { db } from "@/lib/db";
import { apiCache } from "@/lib/db/schema";

export interface CacheStore {
  get<T>(key: string): Promise<T | null>;
  set<T>(key: string, value: T, ttlSeconds: number): Promise<void>;
}

export class SupabaseCacheStore implements CacheStore {
  async get<T>(key: string): Promise<T | null> {
    const rows = await db
      .select({
        value: apiCache.value,
        expiresAt: apiCache.expiresAt,
      })
      .from(apiCache)
      .where(sql`${apiCache.key} = ${key}`)
      .limit(1);

    if (rows.length === 0) return null;

    const row = rows[0];
    if (row.expiresAt.getTime() <= Date.now()) {
      // Lazy eviction — usuń wygasły wpis i zwróć miss.
      await db.delete(apiCache).where(sql`${apiCache.key} = ${key}`);
      return null;
    }

    return row.value as T;
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    const expiresAt = new Date(Date.now() + ttlSeconds * 1000);
    await db
      .insert(apiCache)
      .values({ key, value: value as unknown, expiresAt })
      .onConflictDoUpdate({
        target: apiCache.key,
        set: { value: value as unknown, expiresAt },
      });
  }
}

/** In-memory cache do testów lub w razie potrzeby (np. seed scripty). */
export class InMemoryCacheStore implements CacheStore {
  private store = new Map<string, { value: unknown; expiresAt: number }>();

  async get<T>(key: string): Promise<T | null> {
    const hit = this.store.get(key);
    if (!hit) return null;
    if (hit.expiresAt <= Date.now()) {
      this.store.delete(key);
      return null;
    }
    return hit.value as T;
  }

  async set<T>(key: string, value: T, ttlSeconds: number): Promise<void> {
    this.store.set(key, {
      value,
      expiresAt: Date.now() + ttlSeconds * 1000,
    });
  }
}
