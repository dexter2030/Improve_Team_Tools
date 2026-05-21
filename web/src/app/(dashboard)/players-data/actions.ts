"use server";

import { revalidatePath } from "next/cache";
import { syncAllPlayers, type PlayersFetchOutcome } from "@/lib/players/sync";

export async function syncPlayersAction(): Promise<PlayersFetchOutcome> {
  const outcome = await syncAllPlayers();
  revalidatePath("/players-data");
  return outcome;
}
