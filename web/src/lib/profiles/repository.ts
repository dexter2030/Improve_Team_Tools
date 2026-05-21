/**
 * Repository — mapowanie domain ScoutingProfile ↔ Drizzle rows.
 *
 * DB jest spłaszczone (scouting_profiles + soloq_accounts + proplay_identities).
 * Domain trzyma zagnieżdżony obiekt z .soloq[] + .proplay. Tu jest
 * jedyne miejsce w aplikacji gdzie te dwa modele się stykają.
 */

import "server-only";

import { eq, sql } from "drizzle-orm";
import { db } from "@/lib/db";
import {
  scoutingProfiles,
  soloqAccounts,
  proplayIdentities,
  type ScoutingProfile as DbScoutingProfile,
  type SoloqAccount as DbSoloqAccount,
  type ProplayIdentity as DbProplayIdentity,
} from "@/lib/db/schema";
import type {
  ScoutingProfile,
  SoloQIdentity,
  ProPlayIdentity,
} from "./types";

// --- DB → domain mappers ---------------------------------------------------

function dbSoloqToDomain(row: DbSoloqAccount): SoloQIdentity {
  return {
    riotId: row.riotId,
    platform: row.platform,
    opggUrl: row.opggUrl,
    puuid: row.puuid,
    summonerLevel: row.summonerLevel,
  };
}

function dbProplayToDomain(row: DbProplayIdentity): ProPlayIdentity {
  return {
    leaguepediaLink: row.leaguepediaLink,
    leaguepediaUrl: row.leaguepediaUrl ?? "",
    currentTeam: row.currentTeam,
    verified: row.verified,
  };
}

function rowsToDomain(
  profile: DbScoutingProfile,
  soloqs: DbSoloqAccount[],
  proplay: DbProplayIdentity | null
): ScoutingProfile {
  return {
    profileId: profile.id,
    displayName: profile.displayName,
    role: profile.role,
    soloq: soloqs.map(dbSoloqToDomain),
    proplay: proplay ? dbProplayToDomain(proplay) : null,
    age: profile.age,
    nationality: profile.nationality,
    lolprosUrl: profile.lolprosUrl,
    notes: profile.notes,
    resolutionState: profile.resolutionState,
  };
}

// --- Reads -----------------------------------------------------------------

/** Wszystkie profile z relacjami, sort po createdAt malejąco (najnowsze pierwsze). */
export async function listProfiles(): Promise<ScoutingProfile[]> {
  // Jedno query z LEFT JOIN — Drizzle dla MVP wystarczy klasycznie po stronie JS.
  const profiles = await db
    .select()
    .from(scoutingProfiles)
    .orderBy(sql`${scoutingProfiles.createdAt} DESC`);

  if (profiles.length === 0) return [];

  const profileIds = profiles.map((p) => p.id);
  const [soloqs, proplays] = await Promise.all([
    db
      .select()
      .from(soloqAccounts)
      .where(sql`${soloqAccounts.profileId} IN (${sql.join(profileIds.map((id) => sql`${id}`), sql`, `)})`),
    db
      .select()
      .from(proplayIdentities)
      .where(sql`${proplayIdentities.profileId} IN (${sql.join(profileIds.map((id) => sql`${id}`), sql`, `)})`),
  ]);

  const soloqByProfile = new Map<string, DbSoloqAccount[]>();
  for (const s of soloqs) {
    const arr = soloqByProfile.get(s.profileId) ?? [];
    arr.push(s);
    soloqByProfile.set(s.profileId, arr);
  }
  const proplayByProfile = new Map<string, DbProplayIdentity>();
  for (const p of proplays) proplayByProfile.set(p.profileId, p);

  return profiles.map((p) =>
    rowsToDomain(
      p,
      soloqByProfile.get(p.id) ?? [],
      proplayByProfile.get(p.id) ?? null
    )
  );
}

export async function getProfile(id: string): Promise<ScoutingProfile | null> {
  const [profile] = await db
    .select()
    .from(scoutingProfiles)
    .where(eq(scoutingProfiles.id, id))
    .limit(1);
  if (!profile) return null;

  const [soloqs, proplays] = await Promise.all([
    db.select().from(soloqAccounts).where(eq(soloqAccounts.profileId, id)),
    db
      .select()
      .from(proplayIdentities)
      .where(eq(proplayIdentities.profileId, id))
      .limit(1),
  ]);

  return rowsToDomain(profile, soloqs, proplays[0] ?? null);
}

// --- Writes ----------------------------------------------------------------

/**
 * Insert / replace pełnego profilu (3 tabele) w jednym round-tripie.
 * Idempotentne dla powtórnego resolve'a: ON CONFLICT update.
 */
export async function upsertProfile(profile: ScoutingProfile): Promise<void> {
  // Postgres pooler (Supavisor transaction mode) nie wspiera prepared statements
  // ani multi-statement transakcji w sensie pgClient.transaction. Robimy 3
  // sekwencyjne writes — Drizzle nie rolluje, ale przy crashu w 2/3 mamy
  // partial state. Dla MVP akceptowalne; potem zamienić na pg transaction
  // przez direct connection lub Supabase RPC.
  await db
    .insert(scoutingProfiles)
    .values({
      id: profile.profileId,
      displayName: profile.displayName,
      role: profile.role,
      age: profile.age,
      nationality: profile.nationality,
      lolprosUrl: profile.lolprosUrl,
      notes: profile.notes,
      resolutionState: profile.resolutionState,
    })
    .onConflictDoUpdate({
      target: scoutingProfiles.id,
      set: {
        displayName: profile.displayName,
        role: profile.role,
        age: profile.age,
        nationality: profile.nationality,
        lolprosUrl: profile.lolprosUrl,
        notes: profile.notes,
        resolutionState: profile.resolutionState,
        updatedAt: new Date(),
      },
    });

  // Zastąp soloq całkowicie — prościej niż obliczać diff przy re-resolve.
  await db.delete(soloqAccounts).where(eq(soloqAccounts.profileId, profile.profileId));
  if (profile.soloq.length > 0) {
    await db.insert(soloqAccounts).values(
      profile.soloq.map((s) => ({
        profileId: profile.profileId,
        riotId: s.riotId,
        platform: s.platform,
        opggUrl: s.opggUrl,
        puuid: s.puuid,
        summonerLevel: s.summonerLevel,
        isResolved: s.puuid !== null,
      }))
    );
  }

  // Proplay 0..1 — delete + insert.
  await db
    .delete(proplayIdentities)
    .where(eq(proplayIdentities.profileId, profile.profileId));
  if (profile.proplay) {
    await db.insert(proplayIdentities).values({
      profileId: profile.profileId,
      leaguepediaLink: profile.proplay.leaguepediaLink,
      leaguepediaUrl: profile.proplay.leaguepediaUrl || null,
      currentTeam: profile.proplay.currentTeam,
      verified: profile.proplay.verified,
    });
  }
}

export async function updateNotes(id: string, notes: string): Promise<void> {
  await db
    .update(scoutingProfiles)
    .set({ notes, updatedAt: new Date() })
    .where(eq(scoutingProfiles.id, id));
}

export async function deleteProfile(id: string): Promise<void> {
  // FK CASCADE czyści soloq_accounts + proplay_identities automatycznie.
  await db.delete(scoutingProfiles).where(eq(scoutingProfiles.id, id));
}
