import "server-only";

import { fetchAllPlayers } from "@/lib/leaguepedia/all-players";
import { upsertPlayers, setSyncState } from "./repository";

export interface PlayersFetchOutcome {
  fetched: number;
  saved: number;
  error?: string;
}

export async function syncAllPlayers(): Promise<PlayersFetchOutcome> {
  try {
    const raws = await fetchAllPlayers();
    const saved = await upsertPlayers(
      raws.map((r) => ({
        overviewPage: r.overviewPage,
        id: r.id,
        team: r.team,
        role: r.role,
        country: r.country,
        residency: r.residency,
        nationalityPrimary: r.nationalityPrimary,
        lolpros: r.lolpros,
        isRetired: r.isRetired,
        syncedAt: new Date(),
      }))
    );
    await setSyncState({ lastFetched: new Date(), totalCount: saved });
    return { fetched: raws.length, saved };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { fetched: 0, saved: 0, error: msg };
  }
}
