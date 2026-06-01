/**
 * Snapshot DB → JSON dla backupu.
 *
 * Eksportujemy wszystko poza `api_cache` — ten jest odbudowywany na żywo
 * z TTL, więc nie warto duplikować. Sync-metadata (`league_sync`,
 * `lp_players_sync`, `lp_tournament_players_sync`) zostaje, żeby po
 * restore nie trzeba było re-syncować całej Leaguepedii od zera.
 *
 * Drizzle zwraca `Date` dla timestampów i obiekty dla `jsonb` — oba
 * serializują się natywnie przez `JSON.stringify` (Date → ISO 8601).
 */

import "server-only";

import { db } from "@/lib/db";
import {
  scoutingProfiles,
  soloqAccounts,
  proplayIdentities,
  drafts,
  leagueSync,
  lpPlayersAll,
  lpPlayersSync,
  lpTournamentPlayers,
  lpTournamentPlayersSync,
} from "@/lib/db/schema";

export interface Snapshot {
  /** Bump przy breaking change formatu — restore-script może wybrać ścieżkę. */
  version: 1;
  exportedAt: string;
  tables: {
    scouting_profiles: unknown[];
    soloq_accounts: unknown[];
    proplay_identities: unknown[];
    drafts: unknown[];
    league_sync: unknown[];
    lp_players_all: unknown[];
    lp_players_sync: unknown[];
    lp_tournament_players: unknown[];
    lp_tournament_players_sync: unknown[];
  };
}

export async function buildSnapshot(): Promise<Snapshot> {
  const [
    profiles,
    soloq,
    proplay,
    draftRows,
    leagueSyncRows,
    lpAll,
    lpAllSyncRows,
    lpTp,
    lpTpSyncRows,
  ] = await Promise.all([
    db.select().from(scoutingProfiles),
    db.select().from(soloqAccounts),
    db.select().from(proplayIdentities),
    db.select().from(drafts),
    db.select().from(leagueSync),
    db.select().from(lpPlayersAll),
    db.select().from(lpPlayersSync),
    db.select().from(lpTournamentPlayers),
    db.select().from(lpTournamentPlayersSync),
  ]);

  return {
    version: 1,
    exportedAt: new Date().toISOString(),
    tables: {
      scouting_profiles: profiles,
      soloq_accounts: soloq,
      proplay_identities: proplay,
      drafts: draftRows,
      league_sync: leagueSyncRows,
      lp_players_all: lpAll,
      lp_players_sync: lpAllSyncRows,
      lp_tournament_players: lpTp,
      lp_tournament_players_sync: lpTpSyncRows,
    },
  };
}
