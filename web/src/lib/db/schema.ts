/**
 * Drizzle schema — Improve Team Tools.
 *
 * Trzy tabele dla rdzenia scoutingowego + jedna na cache API:
 *   - scouting_profiles    : profil zawodnika (display name, rola, metadata)
 *   - soloq_accounts       : 0..N kont SoloQ per profil (FK CASCADE)
 *   - proplay_identities   : 0..1 tożsamości pro-play per profil (FK CASCADE)
 *   - api_cache            : KV cache odpowiedzi z Riot / Leaguepedia z TTL
 *
 * Profile nie trzymają zamrożonych statystyk — patrz CLAUDE.md sekcja
 * "Scouting profile = identity keys + metadata, never frozen stats".
 * Tożsamość pro-play joinujemy zawsze po `leaguepedia_link` (canonical
 * wiki page name), nie po in-game handle.
 */

import { sql } from "drizzle-orm";
import {
  boolean,
  index,
  integer,
  jsonb,
  pgEnum,
  pgTable,
  text,
  timestamp,
  unique,
  uuid,
} from "drizzle-orm/pg-core";

export const roleEnum = pgEnum("role", [
  "Top",
  "Jungle",
  "Mid",
  "Bot",
  "Support",
]);

export const resolutionStateEnum = pgEnum("resolution_state", [
  "resolved",
  "partial",
  "failed",
  "unresolved",
]);

// --- scouting_profiles ------------------------------------------------------

export const scoutingProfiles = pgTable("scouting_profiles", {
  id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
  displayName: text("display_name").notNull(),
  role: roleEnum("role").notNull(),
  age: integer("age"),
  nationality: text("nationality"),
  lolprosUrl: text("lolpros_url"),
  notes: text("notes").notNull().default(""),
  resolutionState: resolutionStateEnum("resolution_state")
    .notNull()
    .default("unresolved"),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
  updatedAt: timestamp("updated_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

// --- soloq_accounts ---------------------------------------------------------

export const soloqAccounts = pgTable(
  "soloq_accounts",
  {
    id: uuid("id").primaryKey().default(sql`gen_random_uuid()`),
    profileId: uuid("profile_id")
      .notNull()
      .references(() => scoutingProfiles.id, { onDelete: "cascade" }),
    riotId: text("riot_id").notNull(),
    platform: text("platform").notNull(),
    opggUrl: text("opgg_url"),
    puuid: text("puuid"),
    summonerLevel: integer("summoner_level"),
    isResolved: boolean("is_resolved").notNull().default(false),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [
    // Jeden riot_id na danym serwerze może istnieć tylko raz w profilu —
    // chroni przed duplikatami przy re-resolvie.
    unique("soloq_profile_riot_unique").on(t.profileId, t.riotId, t.platform),
    index("soloq_profile_idx").on(t.profileId),
  ]
);

// --- proplay_identities -----------------------------------------------------

export const proplayIdentities = pgTable("proplay_identities", {
  // profile_id jako PK — wymusza relację 1:0..1 z profilem.
  profileId: uuid("profile_id")
    .primaryKey()
    .references(() => scoutingProfiles.id, { onDelete: "cascade" }),
  leaguepediaLink: text("leaguepedia_link").notNull(),
  leaguepediaUrl: text("leaguepedia_url"),
  currentTeam: text("current_team"),
  verified: boolean("verified").notNull().default(false),
  createdAt: timestamp("created_at", { withTimezone: true })
    .notNull()
    .defaultNow(),
});

// --- api_cache --------------------------------------------------------------

export const apiCache = pgTable(
  "api_cache",
  {
    key: text("key").primaryKey(),
    value: jsonb("value").notNull(),
    expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(),
    createdAt: timestamp("created_at", { withTimezone: true })
      .notNull()
      .defaultNow(),
  },
  (t) => [index("api_cache_expires_idx").on(t.expiresAt)]
);

// --- Typy ze schemy (do użycia w Server Actions / Components) ---------------

export type ScoutingProfile = typeof scoutingProfiles.$inferSelect;
export type NewScoutingProfile = typeof scoutingProfiles.$inferInsert;
export type SoloqAccount = typeof soloqAccounts.$inferSelect;
export type NewSoloqAccount = typeof soloqAccounts.$inferInsert;
export type ProplayIdentity = typeof proplayIdentities.$inferSelect;
export type NewProplayIdentity = typeof proplayIdentities.$inferInsert;
export type Role = (typeof roleEnum.enumValues)[number];
export type ResolutionState = (typeof resolutionStateEnum.enumValues)[number];
