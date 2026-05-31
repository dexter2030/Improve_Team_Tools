/**
 * GET /api/health/riot?riotId=<Game#TAG>&platform=<euw1|kr|...>
 *
 * Sanity-check Riot clienta + cache. Defaultowo resolvuje znanego gracza
 * (Faker — "Hide on bush#KR1" na kr), żeby endpoint dawał sensowny
 * sygnał bez parametrów.
 */

import { getRiotClient } from "@/lib/riot";

export async function GET(request: Request) {
  const url = new URL(request.url);
  const riotId = url.searchParams.get("riotId") ?? "Hide on bush#KR1";
  const platform = url.searchParams.get("platform") ?? "kr";

  try {
    const client = getRiotClient();
    const account = await client.resolveAccount(riotId, platform);
    const ranked = await client.fetchRanked(account.puuid, platform);

    return Response.json({
      ok: true,
      riotId,
      platform,
      account: {
        puuid: account.puuid.slice(0, 16) + "...", // skróć — PUUID jest długi
        summonerLevel: account.summonerLevel,
      },
      ranked: ranked.map((r) => ({
        queueType: r.queueType,
        tier: r.tier,
        rank: r.rank,
        lp: r.lp,
        winRate: r.wins / Math.max(1, r.wins + r.losses),
        games: r.wins + r.losses,
      })),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const name = err instanceof Error ? err.name : "Error";
    return Response.json(
      { ok: false, errorType: name, error: message },
      { status: 500 }
    );
  }
}
