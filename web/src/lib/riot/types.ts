/**
 * Typy domenowe Riot API + mapowanie platform routing → continental routing.
 *
 * Account-V1 i Match-V5 są na continental routing ("regional"),
 * Summoner-V4 i League-V4 są na platform routing. resolveAccount/fetchRanked
 * potrzebują obu, więc tu mapujemy platform → region.
 *
 * OCE (oc1) na Account-V1 nie ma własnego continental — routuje przez americas.
 */

export type PlatformRouting =
  | "na1" | "br1" | "la1" | "la2" | "oc1"
  | "euw1" | "eun1" | "tr1" | "ru"
  | "kr" | "jp1";

export type RegionRouting = "americas" | "europe" | "asia";

export const PLATFORM_TO_REGION: Record<PlatformRouting, RegionRouting> = {
  na1: "americas",
  br1: "americas",
  la1: "americas",
  la2: "americas",
  oc1: "americas",
  euw1: "europe",
  eun1: "europe",
  tr1: "europe",
  ru: "europe",
  kr: "asia",
  jp1: "asia",
};

export const KNOWN_PLATFORMS = Object.keys(
  PLATFORM_TO_REGION
) as PlatformRouting[];

export function isKnownPlatform(value: string): value is PlatformRouting {
  return value in PLATFORM_TO_REGION;
}

// --- Value objects -----------------------------------------------------------

export interface RiotAccount {
  readonly puuid: string;
  readonly summonerLevel: number;
}

export interface RankedEntry {
  readonly queueType: string; // "RANKED_SOLO_5x5" | "RANKED_FLEX_SR"
  readonly tier: string; // "DIAMOND"
  readonly rank: string; // "II"
  readonly lp: number;
  readonly wins: number;
  readonly losses: number;
}

export function games(entry: RankedEntry): number {
  return entry.wins + entry.losses;
}

export function winRate(entry: RankedEntry): number {
  const g = games(entry);
  return g === 0 ? 0 : entry.wins / g;
}

// --- Raw API DTOs (z Riot) ---------------------------------------------------

export interface AccountDto {
  puuid: string;
  gameName?: string;
  tagLine?: string;
}

export interface SummonerDto {
  puuid: string;
  summonerLevel: number;
  profileIconId?: number;
  revisionDate?: number;
}

export interface LeagueEntryDto {
  queueType: string;
  tier: string;
  rank: string;
  leaguePoints: number;
  wins: number;
  losses: number;
}
