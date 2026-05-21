/**
 * Server Actions dla zakładki Scouting.
 *
 * Każda akcja:
 *   1) Waliduje input (parsowanie URLi to walidacja "z założenia").
 *   2) Wywołuje warstwę domain (createProfile / resolver / repository).
 *   3) revalidatePath('/scouting') żeby SSR cache się odświeżył.
 *   4) Zwraca strukturalny wynik dla UI (sukces + raporty / błąd).
 */

"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import {
  createProfile,
  getProfileResolver,
  parseLeaguepediaUrl,
  parseOpggUrl,
  type Role,
  type SoloQIdentity,
  type ProPlayIdentity,
  type SourceReport,
} from "@/lib/profiles";
import {
  upsertProfile,
  updateNotes as repoUpdateNotes,
  deleteProfile as repoDeleteProfile,
} from "@/lib/profiles/repository";

const ROLES: readonly Role[] = ["Top", "Jungle", "Mid", "Bot", "Support"];

export interface AddProfileResult {
  ok: boolean;
  profileId?: string;
  reports?: SourceReport[];
  errors?: string[];
}

export async function addProfileAction(
  formData: FormData
): Promise<AddProfileResult> {
  const errors: string[] = [];

  const displayName = String(formData.get("displayName") ?? "").trim();
  const roleRaw = String(formData.get("role") ?? "").trim();
  const ageRaw = String(formData.get("age") ?? "").trim();
  const nationality =
    String(formData.get("nationality") ?? "").trim() || null;
  const lolprosUrl = String(formData.get("lolprosUrl") ?? "").trim() || null;
  const notes = String(formData.get("notes") ?? "");
  const leaguepediaUrlRaw = String(formData.get("leaguepediaUrl") ?? "").trim();
  const opggRaw = String(formData.get("opggUrls") ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  // Validate role
  if (!ROLES.includes(roleRaw as Role)) {
    errors.push(`Nieznana rola: '${roleRaw}'.`);
  }
  if (!displayName) errors.push("Nazwa gracza jest wymagana.");
  if (opggRaw.length === 0 && !leaguepediaUrlRaw) {
    errors.push(
      "Podaj przynajmniej jeden link op.gg lub link Leaguepedia."
    );
  }

  const age = ageRaw ? Number(ageRaw) : null;
  if (ageRaw && !Number.isFinite(age)) {
    errors.push(`Wiek '${ageRaw}' nie jest liczbą.`);
  }

  // Parse op.gg URLs
  const soloq: SoloQIdentity[] = [];
  for (const url of opggRaw) {
    try {
      const { riotId, platform } = parseOpggUrl(url);
      soloq.push({
        riotId,
        platform,
        opggUrl: url,
        puuid: null,
        summonerLevel: null,
      });
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }

  // Parse Leaguepedia URL
  let proplay: ProPlayIdentity | null = null;
  if (leaguepediaUrlRaw) {
    try {
      const link = parseLeaguepediaUrl(leaguepediaUrlRaw);
      proplay = {
        leaguepediaLink: link,
        leaguepediaUrl: leaguepediaUrlRaw,
        currentTeam: null,
        verified: false,
      };
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }

  if (errors.length > 0) {
    return { ok: false, errors };
  }

  let profile;
  try {
    profile = createProfile({
      displayName,
      role: roleRaw as Role,
      soloq,
      proplay,
      age: age as number | null,
      nationality,
      lolprosUrl,
      notes,
    });
  } catch (err) {
    return {
      ok: false,
      errors: [err instanceof Error ? err.message : String(err)],
    };
  }

  // Resolve identities live — RiotClient + LeaguepediaClient + cache.
  const resolver = getProfileResolver();
  const result = await resolver.resolve(profile);

  // Persist
  await upsertProfile(result.profile);

  revalidatePath("/scouting");

  return {
    ok: true,
    profileId: result.profile.profileId,
    reports: [...result.reports],
  };
}

export async function deleteProfileAction(id: string): Promise<void> {
  await repoDeleteProfile(id);
  revalidatePath("/scouting");
  redirect("/scouting");
}

export async function updateNotesAction(
  id: string,
  notes: string
): Promise<{ ok: true }> {
  await repoUpdateNotes(id, notes);
  revalidatePath(`/scouting/${id}`);
  revalidatePath("/scouting");
  return { ok: true };
}

/**
 * Re-resolve identity dla istniejącego profilu (świeży hit do Riot +
 * Leaguepedia, nadpisuje puuid/level/team itd.). Nie zmienia metadata,
 * notatek ani inputów (riotId/platform/leaguepediaLink).
 */
export async function reResolveAction(id: string): Promise<AddProfileResult> {
  const { getProfile } = await import("@/lib/profiles/repository");
  const profile = await getProfile(id);
  if (!profile) return { ok: false, errors: ["Profil nie istnieje."] };

  // Wyzeruj `is_resolved` flagi żeby resolver faktycznie pobierał na nowo
  // (a nie zwracał "Already resolved" z cache w samym profilu).
  const fresh = {
    ...profile,
    soloq: profile.soloq.map((s) => ({
      ...s,
      puuid: null,
      summonerLevel: null,
    })),
    proplay: profile.proplay
      ? { ...profile.proplay, verified: false, currentTeam: null }
      : null,
  };

  const result = await getProfileResolver().resolve(fresh);
  await upsertProfile(result.profile);
  revalidatePath(`/scouting/${id}`);
  revalidatePath("/scouting");

  return {
    ok: true,
    profileId: result.profile.profileId,
    reports: [...result.reports],
  };
}

/**
 * Edycja profilu — pełen update metadanych + opcjonalna zmiana linków
 * (z re-resolve). Idempotentne dla pustych zmian.
 */
export async function editProfileAction(
  id: string,
  formData: FormData
): Promise<AddProfileResult> {
  const { getProfile } = await import("@/lib/profiles/repository");
  const existing = await getProfile(id);
  if (!existing) return { ok: false, errors: ["Profil nie istnieje."] };

  const errors: string[] = [];

  const displayName = String(formData.get("displayName") ?? "").trim();
  const roleRaw = String(formData.get("role") ?? "").trim();
  const ageRaw = String(formData.get("age") ?? "").trim();
  const nationality =
    String(formData.get("nationality") ?? "").trim() || null;
  const lolprosUrl = String(formData.get("lolprosUrl") ?? "").trim() || null;
  const leaguepediaUrlRaw = String(formData.get("leaguepediaUrl") ?? "").trim();
  const opggRaw = String(formData.get("opggUrls") ?? "")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);

  if (!ROLES.includes(roleRaw as Role)) {
    errors.push(`Nieznana rola: '${roleRaw}'.`);
  }
  if (!displayName) errors.push("Nazwa gracza jest wymagana.");
  if (opggRaw.length === 0 && !leaguepediaUrlRaw) {
    errors.push("Podaj przynajmniej jeden link op.gg lub Leaguepedia.");
  }
  const age = ageRaw ? Number(ageRaw) : null;
  if (ageRaw && !Number.isFinite(age)) {
    errors.push(`Wiek '${ageRaw}' nie jest liczbą.`);
  }

  // Parse nowe op.gg URLs — preservujemy puuid/level dla niezmienionych
  // (riotId+platform dopasowany), nowe dostają puuid=null żeby się
  // resolwowały.
  const existingByRiotId = new Map(
    existing.soloq.map((s) => [`${s.riotId}|${s.platform}`, s])
  );
  const soloq: SoloQIdentity[] = [];
  for (const url of opggRaw) {
    try {
      const { riotId, platform } = parseOpggUrl(url);
      const key = `${riotId}|${platform}`;
      const prev = existingByRiotId.get(key);
      soloq.push({
        riotId,
        platform,
        opggUrl: url,
        puuid: prev?.puuid ?? null,
        summonerLevel: prev?.summonerLevel ?? null,
      });
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }

  let proplay: ProPlayIdentity | null = null;
  if (leaguepediaUrlRaw) {
    try {
      const link = parseLeaguepediaUrl(leaguepediaUrlRaw);
      const prev = existing.proplay;
      const sameLink = prev?.leaguepediaLink === link;
      proplay = {
        leaguepediaLink: link,
        leaguepediaUrl: leaguepediaUrlRaw,
        currentTeam: sameLink ? prev?.currentTeam ?? null : null,
        verified: sameLink ? prev?.verified ?? false : false,
      };
    } catch (err) {
      errors.push(err instanceof Error ? err.message : String(err));
    }
  }

  if (errors.length > 0) return { ok: false, errors };

  // Profile z preservowanym ID + nowymi metadanymi.
  const next = {
    ...existing,
    displayName,
    role: roleRaw as Role,
    age: age as number | null,
    nationality,
    lolprosUrl,
    soloq,
    proplay,
  };

  const result = await getProfileResolver().resolve(next);
  await upsertProfile(result.profile);
  revalidatePath(`/scouting/${id}`);
  revalidatePath("/scouting");

  return {
    ok: true,
    profileId: id,
    reports: [...result.reports],
  };
}
