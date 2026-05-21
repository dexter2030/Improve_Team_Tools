/**
 * LeaguepediaClient — port src/api/leaguepedia_client.py na TypeScript.
 *
 * Skupiony port pokrywający pro-play flow scoutingowego:
 *   - searchPlayersById(inGameName)   → PlayerIdentityRow[]   (resolve handle → link)
 *   - getPlayersMeta(links)           → PlayerMetaRow[]       (Country/Role/IsRetired)
 *   - getPlayerScoreboard(link)       → ScoreboardRow[]       (per-game stats)
 *
 * Reszta endpointów (richer stats, tournament players, picks&bans) zostanie
 * dorzucona razem z draft analyzerem / hidden gems w fazach 7-8.
 *
 * Anon mode (bez bot-passworda). Read-through cache na Supabase api_cache.
 */

import "server-only";

import {
  cargoQuery,
  cargoEscape,
  CargoRow,
  toInt,
  toBool,
  toStr,
} from "./cargo";
import {
  PlayerIdentityRow,
  PlayerMetaRow,
  ScoreboardRow,
  AuthStatus,
} from "./types";
import { CacheStore, SupabaseCacheStore } from "@/lib/riot/cache";

// --- Cache TTLs (zgodne z Python) -------------------------------------------

const PLAYERS_TTL = 24 * 3600;   // 24h — rosters drift between splits
const SCOREBOARD_TTL = 6 * 3600; // 6h — per-game rows immutable, but new games drop in

// --- Klient ----------------------------------------------------------------

export interface LeaguepediaOptions {
  cache?: CacheStore;
  fetcher?: typeof fetch;
}

export class LeaguepediaClient {
  private readonly cache: CacheStore | null;
  private readonly fetcher: typeof fetch;

  constructor(opts: LeaguepediaOptions = {}) {
    this.cache = opts.cache ?? null;
    this.fetcher = opts.fetcher ?? fetch;
  }

  /** Statyczny opis trybu auth — anon-only w MVP. */
  authStatus(): AuthStatus {
    return {
      level: "warn",
      message:
        "Leaguepedia: tryb anonimowy — niski limit API. Bot-password (LEAGUEPEDIA_USERNAME/PASSWORD) zostanie podłączony w kolejnej iteracji.",
    };
  }

  // --- Identity rows ------------------------------------------------------

  /**
   * Players rows where current ID equals `inGameName`.
   * Może zwrócić 0..N — handle bywa reused przez kilku graczy w czasie,
   * UI musi disambiguować.
   */
  async searchPlayersById(inGameName: string): Promise<PlayerIdentityRow[]> {
    const name = inGameName.trim();
    if (!name) return [];
    return this.queryPlayers(`Players.ID='${cargoEscape(name)}'`);
  }

  /** Players rows po canonical link lub team (przynajmniej jeden filtr wymagany). */
  async getPlayers(opts: {
    playerLink?: string;
    team?: string;
  }): Promise<PlayerIdentityRow[]> {
    const clauses: string[] = [];
    if (opts.playerLink) {
      clauses.push(`Players.OverviewPage='${cargoEscape(opts.playerLink)}'`);
    }
    if (opts.team) {
      clauses.push(`Players.Team='${cargoEscape(opts.team)}'`);
    }
    if (clauses.length === 0) {
      throw new Error("getPlayers wymaga playerLink lub team.");
    }
    return this.queryPlayers(clauses.join(" AND "));
  }

  /**
   * Players metadata (Country, Role, IsRetired itd.) batchowane po 30 linków —
   * długie WHERE rozsadziłoby parse limit MediaWiki. Zwraca map link → meta.
   */
  async getPlayersMeta(
    playerLinks: string[]
  ): Promise<Record<string, PlayerMetaRow>> {
    if (playerLinks.length === 0) return {};
    const out: Record<string, PlayerMetaRow> = {};
    const chunkSize = 30;
    for (let i = 0; i < playerLinks.length; i += chunkSize) {
      const window = playerLinks.slice(i, i + chunkSize);
      const ors = window
        .map((p) => `Players.OverviewPage='${cargoEscape(p)}'`)
        .join(" OR ");
      const key = `lp:players_meta:${window.join(",")}`;
      const rows = await this.cargoCached(
        key,
        {
          tables: "Players",
          fields:
            "Players.OverviewPage=OverviewPage,Players.ID=ID,Players.Team=Team," +
            "Players.Role=Role,Players.Country=Country,Players.Residency=Residency," +
            "Players.NationalityPrimary=NationalityPrimary,Players.IsRetired=IsRetired",
          where: ors,
        },
        PLAYERS_TTL
      );
      for (const row of rows) {
        const page = toStr(row.OverviewPage);
        if (page) {
          out[page] = {
            overviewPage: page,
            id: toStr(row.ID),
            team: toStr(row.Team),
            role: toStr(row.Role),
            country: toStr(row.Country),
            residency: toStr(row.Residency),
            nationalityPrimary: toStr(row.NationalityPrimary),
            isRetired: toBool(row.IsRetired),
          };
        }
      }
    }
    return out;
  }

  // --- Scoreboard ---------------------------------------------------------

  /**
   * Per-game wiersze ScoreboardPlayers dla gracza (link = OverviewPage).
   * Zwraca pusty array dla nieistniejących / nierozwiązanych graczy.
   */
  async getPlayerScoreboard(playerLink: string): Promise<ScoreboardRow[]> {
    const link = playerLink.trim();
    if (!link) return [];
    const rows = await this.cargoCached(
      `lp:scoreboard:Link='${cargoEscape(link)}'`,
      {
        tables: "ScoreboardPlayers",
        fields:
          "ScoreboardPlayers.GameId=GameId,ScoreboardPlayers.Champion=Champion," +
          "ScoreboardPlayers.Kills=Kills,ScoreboardPlayers.Deaths=Deaths," +
          "ScoreboardPlayers.Assists=Assists,ScoreboardPlayers.CS=CS," +
          "ScoreboardPlayers.PlayerWin=PlayerWin",
        where: `ScoreboardPlayers.Link='${cargoEscape(link)}'`,
      },
      SCOREBOARD_TTL
    );
    return rows
      .filter((r) => toStr(r.Champion))
      .map((r) => ({
        gameId: toStr(r.GameId),
        champion: toStr(r.Champion),
        kills: toInt(r.Kills),
        deaths: toInt(r.Deaths),
        assists: toInt(r.Assists),
        cs: toInt(r.CS),
        win: toBool(r.PlayerWin),
      }));
  }

  // --- Private ------------------------------------------------------------

  private async queryPlayers(where: string): Promise<PlayerIdentityRow[]> {
    const key = `lp:players:${where}`;
    const rows = await this.cargoCached(
      key,
      {
        tables: "Players",
        fields:
          "Players.OverviewPage=OverviewPage,Players.ID=ID,Players.Team=Team,Players.Role=Role",
        where,
      },
      PLAYERS_TTL
    );
    return rows.map((r) => ({
      link: toStr(r.OverviewPage),
      playerId: toStr(r.ID),
      team: toStr(r.Team),
      role: toStr(r.Role),
    }));
  }

  /**
   * Cargo query z read-through cache. Cache klucz = funkcja parametrów
   * (caller składa unikalny string żeby join/where były w kluczu).
   */
  private async cargoCached(
    key: string,
    query: Parameters<typeof cargoQuery>[0],
    ttlSeconds: number
  ): Promise<CargoRow[]> {
    if (this.cache) {
      const hit = await this.cache.get<CargoRow[]>(key);
      if (hit !== null) return hit;
    }
    const rows = await cargoQuery(query, { fetcher: this.fetcher });
    if (this.cache) await this.cache.set(key, rows, ttlSeconds);
    return rows;
  }
}

// --- Factory (singleton dla server runtime) ---------------------------------

let _singleton: LeaguepediaClient | null = null;

export function getLeaguepediaClient(): LeaguepediaClient {
  if (_singleton) return _singleton;
  _singleton = new LeaguepediaClient({ cache: new SupabaseCacheStore() });
  return _singleton;
}
