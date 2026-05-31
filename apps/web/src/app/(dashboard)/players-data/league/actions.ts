"use server";

import { revalidatePath } from "next/cache";
import {
  syncLeaguePlayers,
  type LeaguePlayersOutcome,
} from "@/lib/players/league-sync";

export async function syncLeaguePlayersAction(
  league: string
): Promise<LeaguePlayersOutcome> {
  const outcome = await syncLeaguePlayers(league);
  revalidatePath("/players-data/league");
  revalidatePath(`/players-data/league/${encodeURIComponent(league)}`);
  return outcome;
}
