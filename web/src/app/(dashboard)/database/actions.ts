"use server";

import { revalidatePath } from "next/cache";
import { fetchLeague } from "@/lib/drafts/sync";
import type { FetchOutcome } from "@/lib/drafts/sync";

export async function syncLeagueAction(
  league: string
): Promise<FetchOutcome> {
  const outcome = await fetchLeague(league);
  revalidatePath("/database");
  revalidatePath("/draft-analyzer");
  return outcome;
}

export async function syncManyLeaguesAction(
  leagues: string[]
): Promise<FetchOutcome[]> {
  const out: FetchOutcome[] = [];
  for (const l of leagues) {
    out.push(await fetchLeague(l));
  }
  revalidatePath("/database");
  revalidatePath("/draft-analyzer");
  return out;
}
