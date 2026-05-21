/**
 * ProfileResolver — port src/processing/resolver.py na TypeScript.
 *
 * Weryfikuje klucze tożsamości świeżego ScoutingProfile przeciwko Riot i
 * Leaguepedia. Stempluje go RESOLVED/PARTIAL/FAILED.
 *
 * Reguły:
 * - Partial failure jest normalne, nie wyjątkowe. NIGDY nie rzuca na błąd
 *   źródła — resolvuje co się da i raportuje resztę.
 * - Coach wkleił dokładne linki, więc to weryfikacja (nie wyszukiwanie).
 * - Resolver to czysty orkiestrator: nie ma własnej logiki API, kompozuje
 *   RiotClient i LeaguepediaClient.
 */

import "server-only";

import {
  ScoutingProfile,
  SoloQIdentity,
  ProPlayIdentity,
  withSoloqAccounts,
  withProplay,
  recomputedState,
  isSoloqResolved,
  isProplayResolved,
} from "./types";
import { RiotClient, NotFoundError, getRiotClient } from "@/lib/riot";
import { LeaguepediaClient, getLeaguepediaClient } from "@/lib/leaguepedia";

// --- Result types ----------------------------------------------------------

export type SourceOutcome = "resolved" | "not_found" | "error" | "skipped";

export interface SourceReport {
  readonly source: string; // 'soloq · GameName#TAG' | 'proplay'
  readonly outcome: SourceOutcome;
  readonly message: string;
}

export function isOk(report: SourceReport): boolean {
  return report.outcome === "resolved";
}

export interface ResolutionResult {
  readonly profile: ScoutingProfile;
  readonly reports: readonly SourceReport[];
}

// --- The resolver ----------------------------------------------------------

export class ProfileResolver {
  constructor(
    private readonly riot: RiotClient,
    private readonly leaguepedia: LeaguepediaClient
  ) {}

  async resolve(profile: ScoutingProfile): Promise<ResolutionResult> {
    const reports: SourceReport[] = [];

    // --- SoloQ accounts (one at a time, kolejność zachowana) ---
    const resolvedAccounts: SoloQIdentity[] = [];
    for (const account of profile.soloq) {
      const { updated, report } = await this.resolveSoloqAccount(account);
      resolvedAccounts.push(updated);
      reports.push(report);
    }
    if (profile.soloq.length === 0) {
      reports.push({
        source: "soloq",
        outcome: "skipped",
        message: "No op.gg accounts on this profile.",
      });
    }

    let working: ScoutingProfile = profile;
    if (profile.soloq.length > 0) {
      working = withSoloqAccounts(working, resolvedAccounts);
    }

    // --- Pro play ---
    if (profile.proplay !== null) {
      const { updated, report } = await this.resolveProplay(working);
      working = updated;
      reports.push(report);
    } else {
      reports.push({
        source: "proplay",
        outcome: "skipped",
        message: "No Leaguepedia link on this profile.",
      });
    }

    // Recompute state z finalnych bloków — all-failed staje się FAILED zamiast UNRESOLVED.
    working = recomputedState(working);
    return { profile: working, reports };
  }

  // -- SoloQ -----------------------------------------------------------------

  private async resolveSoloqAccount(
    account: SoloQIdentity
  ): Promise<{ updated: SoloQIdentity; report: SourceReport }> {
    const source = `soloq · ${account.riotId}`;

    if (isSoloqResolved(account)) {
      return {
        updated: account,
        report: { source, outcome: "resolved", message: "Already resolved." },
      };
    }

    try {
      const riotAccount = await this.riot.resolveAccount(
        account.riotId,
        account.platform
      );
      const updated: SoloQIdentity = {
        ...account,
        puuid: riotAccount.puuid,
        summonerLevel: riotAccount.summonerLevel,
      };
      return {
        updated,
        report: {
          source,
          outcome: "resolved",
          message: `Resolved to PUUID (summoner level ${riotAccount.summonerLevel}).`,
        },
      };
    } catch (err) {
      if (err instanceof NotFoundError) {
        return {
          updated: account,
          report: { source, outcome: "not_found", message: err.message },
        };
      }
      const msg = err instanceof Error ? err.message : String(err);
      return {
        updated: account,
        report: { source, outcome: "error", message: `Riot API error: ${msg}` },
      };
    }
  }

  // -- Pro play --------------------------------------------------------------

  private async resolveProplay(
    profile: ScoutingProfile
  ): Promise<{ updated: ScoutingProfile; report: SourceReport }> {
    const proplay = profile.proplay as ProPlayIdentity;

    if (isProplayResolved(proplay)) {
      return {
        updated: profile,
        report: { source: "proplay", outcome: "resolved", message: "Already verified." },
      };
    }

    try {
      const rows = await this.leaguepedia.getPlayers({
        playerLink: proplay.leaguepediaLink,
      });

      if (rows.length === 0) {
        return {
          updated: profile,
          report: {
            source: "proplay",
            outcome: "not_found",
            message:
              `No Leaguepedia player page '${proplay.leaguepediaLink}'. ` +
              `Check the link points at a player page.`,
          },
        };
      }

      const row = rows[0];
      const verified: ProPlayIdentity = {
        ...proplay,
        currentTeam: row.team || null,
        verified: true,
      };
      const teamNote = row.team ? ` — currently on ${row.team}` : "";
      return {
        updated: withProplay(profile, verified),
        report: {
          source: "proplay",
          outcome: "resolved",
          message: `Verified Leaguepedia page '${proplay.leaguepediaLink}'${teamNote}.`,
        },
      };
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      return {
        updated: profile,
        report: {
          source: "proplay",
          outcome: "error",
          message: `Leaguepedia API error: ${msg}`,
        },
      };
    }
  }
}

// --- Factory ---------------------------------------------------------------

let _singleton: ProfileResolver | null = null;

export function getProfileResolver(): ProfileResolver {
  if (_singleton) return _singleton;
  _singleton = new ProfileResolver(getRiotClient(), getLeaguepediaClient());
  return _singleton;
}
