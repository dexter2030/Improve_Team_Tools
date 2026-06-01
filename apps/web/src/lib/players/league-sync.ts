import "server-only";

import { fetchTournamentPlayers } from "@/lib/leaguepedia/tournament-players";
import { upsertLeaguePlayers } from "./league-repository";

export interface LeaguePlayersOutcome {
  league: string;
  fetched: number;
  saved: number;
  error?: string;
}

export async function syncLeaguePlayers(
  league: string
): Promise<LeaguePlayersOutcome> {
  try {
    const raws = await fetchTournamentPlayers(league);
    const saved = await upsertLeaguePlayers(
      league,
      raws.map((r) => ({
        overviewPage: r.overviewPage,
        league: r.league,
        id: r.id,
        team: r.team,
        role: r.role,
        country: r.country,
        nationalityPrimary: r.nationalityPrimary,
        lastTournament: r.lastTournament,
        lastTournamentStart: r.lastTournamentStart,
        syncedAt: new Date(),
      }))
    );
    return { league, fetched: raws.length, saved };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return { league, fetched: 0, saved: 0, error: msg };
  }
}
