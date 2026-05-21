/**
 * RiotClient — port src/api/riot_client.py na TypeScript.
 *
 * Skupiony port pokrywający dwa flow scoutingowe:
 *   1. resolveAccount(riotId, platform)  → RiotAccount  (Account-V1 + Summoner-V4)
 *   2. fetchRanked(puuid, platform)      → RankedEntry[] (League-V4)
 *
 * Match-V5 (matchlist, match, timeline) NIE jest jeszcze portowany — obecne UI
 * scoutingowe go nie używa. Dodać gdy będzie zakładka analityczna.
 *
 * Server-only: ten moduł nigdy nie powinien trafić do bundla klienta, bo
 * trzyma RIOT_API_KEY w nagłówku.
 */

import "server-only";

import {
  PLATFORM_TO_REGION,
  PlatformRouting,
  RegionRouting,
  RiotAccount,
  RankedEntry,
  AccountDto,
  SummonerDto,
  LeagueEntryDto,
  isKnownPlatform,
  KNOWN_PLATFORMS,
} from "./types";
import {
  RiotApiError,
  NotFoundError,
  UnauthorizedError,
  RateLimitError,
} from "./errors";
import { CacheStore, SupabaseCacheStore } from "./cache";

// --- TTLs (zgodne z Python src/api/riot_client.py) ---------------------------

const ACCOUNT_TTL = 30 * 24 * 3600;   // 30 dni — Riot ID → PUUID praktycznie stałe
const SUMMONER_TTL = 24 * 3600;       // 24h — summoner level zmienia się powoli
const RANKED_TTL = 3600;              // 1h — LP/tier może się zmienić w trakcie gry

// --- Pomocnicze --------------------------------------------------------------

function regionFor(platform: PlatformRouting): RegionRouting {
  return PLATFORM_TO_REGION[platform];
}

function validatePlatform(value: string): PlatformRouting {
  const normalized = value.trim().toLowerCase();
  if (!isKnownPlatform(normalized)) {
    throw new RiotApiError(
      `Unknown platform '${value}'. Known: ${KNOWN_PLATFORMS.join(", ")}.`,
      400
    );
  }
  return normalized;
}

function splitRiotId(riotId: string): { gameName: string; tagLine: string } {
  const idx = riotId.indexOf("#");
  if (idx < 0) {
    throw new RiotApiError(
      `Riot ID '${riotId}' must be in 'GameName#TAG' form.`,
      400
    );
  }
  const gameName = riotId.slice(0, idx).trim();
  const tagLine = riotId.slice(idx + 1).trim();
  if (!gameName || !tagLine) {
    throw new RiotApiError(
      `Riot ID '${riotId}' must be in 'GameName#TAG' form.`,
      400
    );
  }
  return { gameName, tagLine };
}

// --- RiotClient --------------------------------------------------------------

export interface RiotClientOptions {
  apiKey: string;
  cache?: CacheStore;
  /** Custom fetch — głównie do testów (mock). */
  fetcher?: typeof fetch;
}

export class RiotClient {
  private readonly apiKey: string;
  private readonly cache: CacheStore | null;
  private readonly fetcher: typeof fetch;

  constructor(opts: RiotClientOptions) {
    if (!opts.apiKey) {
      throw new RiotApiError("apiKey must be set.", 400);
    }
    this.apiKey = opts.apiKey;
    this.cache = opts.cache ?? null;
    this.fetcher = opts.fetcher ?? fetch;
  }

  // -- Public API ----------------------------------------------------------

  /**
   * Riot ID → PUUID + summoner level. Łączy Account-V1 (continental) +
   * Summoner-V4 (platform).
   */
  async resolveAccount(
    riotId: string,
    platform: string
  ): Promise<RiotAccount> {
    const plat = validatePlatform(platform);
    const region = regionFor(plat);
    const { gameName, tagLine } = splitRiotId(riotId);

    const account = await this.fetchAccount(region, gameName, tagLine);
    const summoner = await this.fetchSummoner(plat, account.puuid);

    return {
      puuid: account.puuid,
      summonerLevel: summoner.summonerLevel,
    };
  }

  /**
   * League-V4 by-puuid → wszystkie wpisy ranked dla gracza (zwykle 0–2:
   * SoloQ i/lub Flex). Pusta lista, jeśli gracz unranked.
   */
  async fetchRanked(
    puuid: string,
    platform: string
  ): Promise<RankedEntry[]> {
    const plat = validatePlatform(platform);
    const key = `riot:ranked:${plat}:${puuid}`;

    const cached = await this.cacheGet<RankedEntry[]>(key);
    if (cached !== null) return cached;

    let entries: LeagueEntryDto[];
    try {
      entries = await this.request<LeagueEntryDto[]>(
        `https://${plat}.api.riotgames.com/lol/league/v4/entries/by-puuid/${puuid}`
      );
    } catch (err) {
      if (err instanceof NotFoundError) {
        entries = [];
      } else {
        throw err;
      }
    }

    const result: RankedEntry[] = entries.map((e) => ({
      queueType: e.queueType,
      tier: e.tier,
      rank: e.rank,
      lp: e.leaguePoints,
      wins: e.wins,
      losses: e.losses,
    }));
    await this.cacheSet(key, result, RANKED_TTL);
    return result;
  }

  // -- Endpoint helpers ----------------------------------------------------

  private async fetchAccount(
    region: RegionRouting,
    gameName: string,
    tagLine: string
  ): Promise<AccountDto> {
    const key = `riot:account:${region}:${gameName.toLowerCase()}#${tagLine.toLowerCase()}`;
    const cached = await this.cacheGet<AccountDto>(key);
    if (cached !== null) return cached;

    const url =
      `https://${region}.api.riotgames.com/riot/account/v1/accounts/by-riot-id/` +
      `${encodeURIComponent(gameName)}/${encodeURIComponent(tagLine)}`;

    try {
      const account = await this.request<AccountDto>(url);
      await this.cacheSet(key, account, ACCOUNT_TTL);
      return account;
    } catch (err) {
      if (err instanceof NotFoundError) {
        throw new NotFoundError(
          `No Riot account for '${gameName}#${tagLine}' on region '${region}'.`
        );
      }
      throw err;
    }
  }

  private async fetchSummoner(
    platform: PlatformRouting,
    puuid: string
  ): Promise<SummonerDto> {
    const key = `riot:summoner:${platform}:${puuid}`;
    const cached = await this.cacheGet<SummonerDto>(key);
    if (cached !== null) return cached;

    const url = `https://${platform}.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/${puuid}`;

    try {
      const summoner = await this.request<SummonerDto>(url);
      await this.cacheSet(key, summoner, SUMMONER_TTL);
      return summoner;
    } catch (err) {
      if (err instanceof NotFoundError) {
        throw new NotFoundError(
          `Riot account resolved, but no League summoner on platform '${platform}'.`
        );
      }
      throw err;
    }
  }

  // -- Request layer -------------------------------------------------------

  /**
   * Wykonuje request z X-Riot-Token i mapuje statusy na typed errors.
   * Pojedynczy retry na 429 (Retry-After), bez dodatkowego backoffu —
   * to MVP. Pełny rate-limiter dorobimy gdy będzie potrzeba.
   */
  private async request<T>(url: string): Promise<T> {
    const res = await this.fetcher(url, {
      headers: { "X-Riot-Token": this.apiKey },
      cache: "no-store", // własny cache obsługuje TTL; nie chcemy Next-cache do API key
    });

    if (res.ok) {
      return (await res.json()) as T;
    }

    let body: unknown;
    try {
      body = await res.json();
    } catch {
      body = await res.text().catch(() => undefined);
    }

    switch (res.status) {
      case 401:
      case 403:
        throw new UnauthorizedError(body);
      case 404:
        throw new NotFoundError(`Riot API returned 404 for ${url}`, body);
      case 429: {
        const retryAfter = Number(res.headers.get("Retry-After") ?? "1");
        throw new RateLimitError(Number.isFinite(retryAfter) ? retryAfter : 1, body);
      }
      default:
        throw new RiotApiError(
          `Riot API returned ${res.status} for ${url}`,
          res.status,
          body
        );
    }
  }

  // -- Cache passthroughs --------------------------------------------------

  private async cacheGet<T>(key: string): Promise<T | null> {
    return this.cache ? this.cache.get<T>(key) : null;
  }

  private async cacheSet<T>(
    key: string,
    value: T,
    ttlSeconds: number
  ): Promise<void> {
    if (this.cache) await this.cache.set(key, value, ttlSeconds);
  }
}

// --- Factory (server) --------------------------------------------------------

/**
 * Domyślny singleton używany w Server Components i Server Actions.
 * Czyta klucz z env w momencie wywołania (nie w module top-level), żeby
 * brak klucza nie wybijał całego procesu przy buildzie.
 */
let _singleton: RiotClient | null = null;

export function getRiotClient(): RiotClient {
  if (_singleton) return _singleton;
  const apiKey = process.env.RIOT_API_KEY;
  if (!apiKey) {
    throw new RiotApiError(
      "RIOT_API_KEY is not set. Add it to web/.env.local or Vercel env vars.",
      500
    );
  }
  _singleton = new RiotClient({
    apiKey,
    cache: new SupabaseCacheStore(),
  });
  return _singleton;
}
