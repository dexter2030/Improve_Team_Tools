/**
 * Sync — pobiera drafty z Leaguepedia i upsertuje do DB.
 *
 * Bazujemy na dacie game_date jako kursorze przyrostowym, ale Leaguepedia
 * Cargo nie obsługuje filtra > date w prosty sposób bez wpływu na join.
 * Dla uproszczenia MVP: każdy fetch pobiera całą ligę (max 20k), upsert
 * deduplikuje. Drogie, ale poprawne. Przyrostowość zrobimy potem.
 */

import "server-only";

import { fetchDrafts } from "@/lib/leaguepedia/drafts";
import { upsertDrafts, upsertLeagueSync } from "./repository";

export interface FetchOutcome {
  league: string;
  fetched: number;
  saved: number;
  error?: string;
}

export async function fetchLeague(league: string): Promise<FetchOutcome> {
  try {
    const raws = await fetchDrafts(league, "", 20000);
    const saved = await upsertDrafts(raws);
    const maxGameDate = raws.reduce<Date | null>((acc, r) => {
      if (!r.gameDate) return acc;
      if (!acc || r.gameDate.getTime() > acc.getTime()) return r.gameDate;
      return acc;
    }, null);
    await upsertLeagueSync({
      league,
      lastFetched: new Date(),
      lastGameDate: maxGameDate,
    });
    return { league, fetched: raws.length, saved };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { league, fetched: 0, saved: 0, error: msg };
  }
}
