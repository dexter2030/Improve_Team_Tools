/**
 * Ranked panel — fetch League-V4 dla każdego SoloQ account z PUUID.
 * Server Component (osobny plik = osobny Suspense boundary).
 *
 * Renderuje per-account tabelę queue × tier × LP × WR × games.
 * Tier-y kolorowane wg standardu (Challenger ~gold, Diamond ~cyan itd.).
 */

import { getRiotClient } from "@/lib/riot";
import type { SoloQIdentity } from "@/lib/profiles";

const TIER_COLOR: Record<string, string> = {
  CHALLENGER: "text-amber-600",
  GRANDMASTER: "text-rose-600",
  MASTER: "text-fuchsia-600",
  DIAMOND: "text-cyan-600",
  EMERALD: "text-emerald-600",
  PLATINUM: "text-teal-600",
  GOLD: "text-yellow-600",
  SILVER: "text-slate-500",
  BRONZE: "text-orange-700",
  IRON: "text-zinc-500",
};

const QUEUE_LABEL: Record<string, string> = {
  RANKED_SOLO_5x5: "SoloQ",
  RANKED_FLEX_SR: "Flex",
};

export async function RankedPanel({ accounts }: { accounts: readonly SoloQIdentity[] }) {
  const resolved = accounts.filter((a) => a.puuid !== null);
  if (resolved.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Brak rozwiązanych kont SoloQ — ranked data niedostępna.
      </p>
    );
  }

  const client = getRiotClient();
  const blocks = await Promise.all(
    resolved.map(async (a) => {
      try {
        const entries = await client.fetchRanked(a.puuid!, a.platform);
        const sr = entries
          .filter((e) => e.queueType in QUEUE_LABEL)
          .sort((x, y) => tierOrder(x.tier) - tierOrder(y.tier));
        return { account: a, entries: sr, error: null as string | null };
      } catch (err) {
        return {
          account: a,
          entries: [],
          error: err instanceof Error ? err.message : String(err),
        };
      }
    })
  );

  return (
    <div className="space-y-4">
      {blocks.map(({ account, entries, error }) => (
        <div key={`${account.platform}:${account.riotId}`} className="space-y-2">
          <div className="flex items-center gap-2 text-sm">
            <code className="bg-muted px-2 py-0.5 rounded text-xs font-medium">
              {account.riotId}
            </code>
            <span className="text-muted-foreground text-xs">· {account.platform}</span>
          </div>
          {error ? (
            <p className="text-sm text-amber-700 dark:text-amber-400">
              Nie udało się pobrać: {error}
            </p>
          ) : entries.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Unranked — brak gier ranked w tym sezonie.
            </p>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {entries.map((e) => {
                const games = e.wins + e.losses;
                const wr = games === 0 ? 0 : (e.wins / games) * 100;
                return (
                  <div
                    key={e.queueType}
                    className="border rounded-lg p-3 bg-card"
                  >
                    <div className="flex items-baseline justify-between mb-2">
                      <span className="text-xs uppercase text-muted-foreground tracking-wider">
                        {QUEUE_LABEL[e.queueType] ?? e.queueType}
                      </span>
                      <span className={`text-sm font-semibold ${TIER_COLOR[e.tier.toUpperCase()] ?? ""}`}>
                        {e.tier} {e.rank}
                      </span>
                    </div>
                    <div className="grid grid-cols-3 gap-2 text-xs">
                      <Stat label="LP" value={e.lp.toString()} />
                      <Stat label="WR" value={`${wr.toFixed(0)}%`} />
                      <Stat label="Games" value={games.toString()} />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-muted-foreground">{label}</div>
      <div className="font-medium tabular-nums">{value}</div>
    </div>
  );
}

function tierOrder(t: string): number {
  const order: Record<string, number> = {
    CHALLENGER: 0, GRANDMASTER: 1, MASTER: 2,
    DIAMOND: 3, EMERALD: 4, PLATINUM: 5,
    GOLD: 6, SILVER: 7, BRONZE: 8, IRON: 9,
  };
  return order[t.toUpperCase()] ?? 99;
}
