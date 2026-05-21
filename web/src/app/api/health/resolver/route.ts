/**
 * GET /api/health/resolver
 *
 * Live test pełnego resolvera: tworzy profil Fakera z op.gg + Leaguepedia
 * linkiem, resolvuje przeciw Riot + Leaguepedia, zwraca wynik.
 */

import {
  createProfile,
  getProfileResolver,
  parseLeaguepediaUrl,
  parseOpggUrl,
} from "@/lib/profiles";

export async function GET() {
  try {
    const opgg = parseOpggUrl(
      "https://op.gg/lol/summoners/kr/Hide%20on%20bush-KR1"
    );
    const leaguepediaLink = parseLeaguepediaUrl(
      "https://lol.fandom.com/wiki/Faker"
    );

    const profile = createProfile({
      displayName: "Faker (live test)",
      role: "Mid",
      soloq: [
        {
          riotId: opgg.riotId,
          platform: opgg.platform,
          opggUrl: "https://op.gg/lol/summoners/kr/Hide%20on%20bush-KR1",
          puuid: null,
          summonerLevel: null,
        },
      ],
      proplay: {
        leaguepediaLink,
        leaguepediaUrl: "https://lol.fandom.com/wiki/Faker",
        currentTeam: null,
        verified: false,
      },
    });

    const resolver = getProfileResolver();
    const result = await resolver.resolve(profile);

    return Response.json({
      ok: true,
      resolutionState: result.profile.resolutionState,
      reports: result.reports,
      profile: {
        displayName: result.profile.displayName,
        role: result.profile.role,
        soloq: result.profile.soloq.map((s) => ({
          riotId: s.riotId,
          platform: s.platform,
          summonerLevel: s.summonerLevel,
          resolved: s.puuid !== null,
        })),
        proplay: result.profile.proplay
          ? {
              link: result.profile.proplay.leaguepediaLink,
              team: result.profile.proplay.currentTeam,
              verified: result.profile.proplay.verified,
            }
          : null,
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
}
