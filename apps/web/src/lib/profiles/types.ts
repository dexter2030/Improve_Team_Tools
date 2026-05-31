/**
 * Domain types dla profili scoutingowych.
 *
 * Powtarza model z src/processing/profiles.py — profil trzyma TYLKO klucze
 * tożsamości + scouting metadata, NIGDY zamrożonych statystyk (te są
 * fetched fresh każdorazowo i cohort-relative).
 *
 * Te typy NIE są tym samym co rows z Drizzle schemy (DB rows są flat:
 * scouting_profiles + soloq_accounts + proplay_identities). Mapowanie
 * DB ↔ domain żyje w Server Actions w fazach UI.
 */

import type { Role, ResolutionState } from "@/lib/db/schema";

export type { Role, ResolutionState };

// --- Identity blocks --------------------------------------------------------

export interface SoloQIdentity {
  readonly riotId: string; // "GameName#TAG"
  readonly platform: string; // "euw1", "kr", ...
  readonly opggUrl: string | null;
  readonly puuid: string | null;
  readonly summonerLevel: number | null;
}

export function isSoloqResolved(s: SoloQIdentity): boolean {
  return s.puuid !== null;
}

export interface ProPlayIdentity {
  readonly leaguepediaLink: string; // canonical wiki page name (join key)
  readonly leaguepediaUrl: string;
  readonly currentTeam: string | null;
  readonly verified: boolean;
}

export function isProplayResolved(p: ProPlayIdentity): boolean {
  return p.verified;
}

// --- Profile ---------------------------------------------------------------

export interface ScoutingProfile {
  readonly profileId: string;
  readonly displayName: string;
  readonly role: Role;
  readonly soloq: readonly SoloQIdentity[];
  readonly proplay: ProPlayIdentity | null;
  readonly age: number | null;
  readonly nationality: string | null;
  readonly lolprosUrl: string | null;
  readonly notes: string;
  readonly resolutionState: ResolutionState;
}

// --- Construction ----------------------------------------------------------

export interface CreateProfileInput {
  displayName: string;
  role: Role;
  soloq?: readonly SoloQIdentity[];
  proplay?: ProPlayIdentity | null;
  age?: number | null;
  nationality?: string | null;
  lolprosUrl?: string | null;
  notes?: string;
  profileId?: string; // pomijaj — domyślnie crypto.randomUUID()
}

export function createProfile(input: CreateProfileInput): ScoutingProfile {
  const soloq = input.soloq ?? [];
  const proplay = input.proplay ?? null;
  if (soloq.length === 0 && proplay === null) {
    throw new Error(
      "A profile needs at least one source identity — an op.gg account and/or a Leaguepedia link."
    );
  }
  if (input.age != null && (input.age < 12 || input.age > 60)) {
    throw new Error(`Implausible age ${input.age}; expected 12-60.`);
  }

  const profile: ScoutingProfile = {
    profileId: input.profileId ?? crypto.randomUUID(),
    displayName: input.displayName.trim(),
    role: input.role,
    soloq,
    proplay,
    age: input.age ?? null,
    nationality: input.nationality ?? null,
    lolprosUrl: input.lolprosUrl ?? null,
    notes: input.notes ?? "",
    resolutionState: "unresolved",
  };
  return profile;
}

// --- Immutable mutators ----------------------------------------------------

export function withSoloqAccounts(
  profile: ScoutingProfile,
  accounts: readonly SoloQIdentity[]
): ScoutingProfile {
  return { ...profile, soloq: accounts };
}

export function withProplay(
  profile: ScoutingProfile,
  proplay: ProPlayIdentity
): ScoutingProfile {
  if (profile.proplay === null) {
    throw new Error("Profile has no pro-play identity to update.");
  }
  return { ...profile, proplay };
}

export function withNotes(
  profile: ScoutingProfile,
  notes: string
): ScoutingProfile {
  return { ...profile, notes };
}

/**
 * Recompute resolutionState z bloków tożsamości.
 *
 * Każdy SoloQ account i proplay block liczy się jako 1 blok:
 *   - próba weryfikacji, nic nie resolved → FAILED
 *   - wszystko resolved → RESOLVED
 *   - część resolved, część nie → PARTIAL
 *
 * Wołać po każdym przejściu resolvera, włącznie ze ścieżką all-failed,
 * żeby zamiast domyślnego "unresolved" wyszło "failed".
 */
export function recomputedState(profile: ScoutingProfile): ScoutingProfile {
  const blocks: Array<{ resolved: boolean }> = [
    ...profile.soloq.map((s) => ({ resolved: isSoloqResolved(s) })),
    ...(profile.proplay ? [{ resolved: isProplayResolved(profile.proplay) }] : []),
  ];

  if (blocks.length === 0) {
    return { ...profile, resolutionState: "unresolved" };
  }

  const resolved = blocks.filter((b) => b.resolved).length;
  let state: ResolutionState;
  if (resolved === 0) state = "failed";
  else if (resolved === blocks.length) state = "resolved";
  else state = "partial";

  return { ...profile, resolutionState: state };
}
