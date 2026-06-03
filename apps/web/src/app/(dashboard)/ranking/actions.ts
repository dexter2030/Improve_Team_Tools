"use server";

import { revalidatePath } from "next/cache";
import { syncLeagueStats, type StatsFetchOutcome } from "@/lib/ranking/stats-sync";

export async function syncLeagueStatsAction(
  league: string
): Promise<StatsFetchOutcome> {
  const outcome = await syncLeagueStats(league);
  revalidatePath("/ranking");
  revalidatePath(`/ranking/${encodeURIComponent(league)}`);
  return outcome;
}
