/**
 * Cargo — surowe statystyki meczowe graczy (ScoreboardPlayers + ScoreboardGames).
 *
 * Join: ScoreboardPlayers.GameId = ScoreboardGames.GameId. Z ScoreboardGames
 * bierzemy datę (DateTime_UTC → rok), długość gry (do CS/min, DPM) i Tournament
 * (filtr ligi). To FETCH ONLY — agregacja per rok i scoring są w src/lib/ranking/.
 *
 * Filtr ligi jak w drafts.ts: Tournament LIKE '%liga%' + wykluczenia
 * moreSpecific() (żeby "LFL" nie łapało "LFL Division 2"). `league` w zwracanym
 * wierszu to krótka nazwa, którą pytaliśmy — nie surowy Tournament — żeby
 * kohorty w scoringu grupowały się czysto.
 */

import {
  cargoEscape,
  cargoPaginated,
  toBool,
  toFloat,
  toInt,
  toStr,
  type CargoRow,
} from "./cargo";
import { moreSpecific } from "./leagues";
import type { ScoreboardPlayerRow } from "./types";

const SCOREBOARD_FIELDS = [
  "ScoreboardPlayers.Link=Link",
  "ScoreboardPlayers.Role=Role",
  "ScoreboardPlayers.Kills=Kills",
  "ScoreboardPlayers.Deaths=Deaths",
  "ScoreboardPlayers.Assists=Assists",
  "ScoreboardPlayers.CS=CS",
  "ScoreboardPlayers.Gold=Gold",
  "ScoreboardPlayers.DamageToChampions=Damage",
  "ScoreboardPlayers.TeamKills=TeamKills",
  "ScoreboardPlayers.TeamGold=TeamGold",
  "ScoreboardPlayers.PlayerWin=PlayerWin",
  "ScoreboardGames.DateTime_UTC=DateTime",
  "ScoreboardGames.Gamelength_Number=GameLength",
].join(",");

const SCOREBOARD_JOIN_ON = "ScoreboardPlayers.GameId=ScoreboardGames.GameId";

export interface FetchScoreboardOpts {
  /** Tylko mecze od tego roku włącznie (okno kariery). */
  sinceYear?: number;
  /** Twardy limit wierszy (ScoreboardPlayers = 10 wierszy/mecz). */
  maxRows?: number;
}

/**
 * Wszystkie wiersze ScoreboardPlayers dla ligi (opcjonalnie od `sinceYear`).
 * Jedno paginowane zapytanie obejmuje całą ligę naraz — tanio względem
 * rate-limitu (nie per gracz).
 */
export async function fetchScoreboardPlayers(
  league: string,
  opts: FetchScoreboardOpts = {}
): Promise<ScoreboardPlayerRow[]> {
  const { sinceYear, maxRows = 40000 } = opts;
  const escaped = cargoEscape(league);
  const exclusions = moreSpecific(league)
    .map((m) => `ScoreboardGames.Tournament NOT LIKE '%${cargoEscape(m)}%'`)
    .join(" AND ");

  const whereParts = [
    `ScoreboardGames.Tournament LIKE '%${escaped}%'`,
    ...(exclusions ? [exclusions] : []),
    ...(sinceYear
      ? [`ScoreboardGames.DateTime_UTC >= '${sinceYear}-01-01 00:00:00'`]
      : []),
  ];

  const rows = await cargoPaginated(
    {
      tables: "ScoreboardPlayers,ScoreboardGames",
      fields: SCOREBOARD_FIELDS,
      where: whereParts.join(" AND "),
      joinOn: SCOREBOARD_JOIN_ON,
      orderBy: "ScoreboardGames.DateTime_UTC DESC",
    },
    maxRows
  );

  return rows
    .map((r) => normalize(r, league))
    .filter((r): r is ScoreboardPlayerRow => r !== null);
}

function normalize(row: CargoRow, league: string): ScoreboardPlayerRow | null {
  const link = toStr(row.Link);
  if (!link) return null;
  const date = parseUtc(row.DateTime);
  if (!date) return null; // bez daty nie da się przypisać sezonu (roku)

  const gameLength = toFloat(row.GameLength);
  return {
    link,
    role: toStr(row.Role) || null,
    year: date.getUTCFullYear(),
    league,
    win: toBool(row.PlayerWin),
    gameLength: gameLength > 0 ? gameLength : null,
    kills: toInt(row.Kills),
    deaths: toInt(row.Deaths),
    assists: toInt(row.Assists),
    cs: toInt(row.CS),
    gold: toInt(row.Gold),
    damage: toInt(row.Damage),
    teamKills: toInt(row.TeamKills),
    teamGold: toInt(row.TeamGold),
  };
}

function parseUtc(value: unknown): Date | null {
  const s = toStr(value);
  if (!s) return null;
  // Leaguepedia DateTime_UTC: "2025-01-15 18:00:00".
  const iso = s.includes("T") ? s : s.replace(" ", "T") + "Z";
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d : null;
}
