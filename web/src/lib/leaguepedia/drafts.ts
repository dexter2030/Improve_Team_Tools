/**
 * Cargo extension — pobieranie draftów (PicksAndBansS7 + ScoreboardGames
 * + MatchScheduleGame).
 *
 * Join: PicksAndBansS7.GameId = ScoreboardGames.GameId
 *     + ScoreboardGames.GameId = MatchScheduleGame.GameId.
 *
 * Z MatchScheduleGame bierzemy `Blue`, `Red`, `FirstPick` żeby obliczyć
 * `firstPickSide` — od 2026 LEC/LCK strony i first-pick mogą być różne
 * drużynami. Pre-2026 `FirstPick` jest puste w LP → zostawiamy null
 * (analyzer traktuje to jak 'blue', bo stara zasada Blue=first).
 */

import { cargoQuery, cargoEscape, cargoPaginated, toStr, type CargoRow } from "./cargo";
import { moreSpecific } from "./leagues";

export interface RawDraft {
  matchId: string;
  patch: string | null;
  league: string;
  gameDate: Date | null;
  blueTeam: string | null;
  redTeam: string | null;
  blueBans: string[];
  redBans: string[];
  b1Pick: string | null;
  r1Pick: string | null;
  r2Pick: string | null;
  b2Pick: string | null;
  b3Pick: string | null;
  r3Pick: string | null;
  b4Pick: string | null;
  b5Pick: string | null;
  r4Pick: string | null;
  r5Pick: string | null;
  firstPickSide: "blue" | "red" | null;
  winner: string | null;
}

const PICK_BAN_FIELDS = [
  "PicksAndBansS7.GameId=GameId",
  "PicksAndBansS7.Team1Ban1=t1b1",
  "PicksAndBansS7.Team1Ban2=t1b2",
  "PicksAndBansS7.Team1Ban3=t1b3",
  "PicksAndBansS7.Team1Ban4=t1b4",
  "PicksAndBansS7.Team1Ban5=t1b5",
  "PicksAndBansS7.Team2Ban1=t2b1",
  "PicksAndBansS7.Team2Ban2=t2b2",
  "PicksAndBansS7.Team2Ban3=t2b3",
  "PicksAndBansS7.Team2Ban4=t2b4",
  "PicksAndBansS7.Team2Ban5=t2b5",
  "PicksAndBansS7.Team1Pick1=t1p1",
  "PicksAndBansS7.Team1Pick2=t1p2",
  "PicksAndBansS7.Team1Pick3=t1p3",
  "PicksAndBansS7.Team1Pick4=t1p4",
  "PicksAndBansS7.Team1Pick5=t1p5",
  "PicksAndBansS7.Team2Pick1=t2p1",
  "PicksAndBansS7.Team2Pick2=t2p2",
  "PicksAndBansS7.Team2Pick3=t2p3",
  "PicksAndBansS7.Team2Pick4=t2p4",
  "PicksAndBansS7.Team2Pick5=t2p5",
  "ScoreboardGames.Tournament=Tournament",
  "ScoreboardGames.OverviewPage=OverviewPage",
  "ScoreboardGames.Patch=Patch",
  "ScoreboardGames.DateTime_UTC=DateTime",
  "ScoreboardGames.Team1=Team1",
  "ScoreboardGames.Team2=Team2",
  "ScoreboardGames.Winner=Winner",
  "MatchScheduleGame.Blue=MsgBlue",
  "MatchScheduleGame.Red=MsgRed",
  "MatchScheduleGame.FirstPick=MsgFirstPick",
].join(",");

const DRAFTS_JOIN_ON =
  "PicksAndBansS7.GameId=ScoreboardGames.GameId,ScoreboardGames.GameId=MatchScheduleGame.GameId";

/**
 * Iteruje porcje draftów dla danej ligi. Filtr po Tournament LIKE '%league%'
 * z wykluczeniem bardziej szczegółowych nazw (więcej → moreSpecific()).
 *
 * @param league — krótka nazwa, np. "LEC"
 * @param seasonWhere — opcjonalny dodatkowy fragment WHERE
 * @param maxRows — limit całkowity (default 20000)
 */
export async function fetchDrafts(
  league: string,
  seasonWhere = "",
  maxRows = 20000
): Promise<RawDraft[]> {
  const escaped = cargoEscape(league);
  const exclusions = moreSpecific(league)
    .map((m) => `ScoreboardGames.Tournament NOT LIKE '%${cargoEscape(m)}%'`)
    .join(" AND ");

  const whereParts = [
    `ScoreboardGames.Tournament LIKE '%${escaped}%'`,
    ...(exclusions ? [exclusions] : []),
    ...(seasonWhere ? [seasonWhere] : []),
  ];

  const rows = await cargoPaginated(
    {
      tables: "PicksAndBansS7,ScoreboardGames,MatchScheduleGame",
      fields: PICK_BAN_FIELDS,
      where: whereParts.join(" AND "),
      joinOn: DRAFTS_JOIN_ON,
      orderBy: "ScoreboardGames.DateTime_UTC DESC",
    },
    maxRows
  );

  return rows.map(normalize).filter(hasAnyPick);
}

/**
 * Liczba dostępnych draftów na Leaguepedia dla danej ligi — używana do
 * pokazania "kompletności" w UI Database.
 */
export async function countDrafts(league: string): Promise<number> {
  const escaped = cargoEscape(league);
  const exclusions = moreSpecific(league)
    .map((m) => `ScoreboardGames.Tournament NOT LIKE '%${cargoEscape(m)}%'`)
    .join(" AND ");
  const whereParts = [
    `ScoreboardGames.Tournament LIKE '%${escaped}%'`,
    ...(exclusions ? [exclusions] : []),
  ];
  const rows = await cargoQuery({
    tables: "PicksAndBansS7,ScoreboardGames",
    fields: "COUNT(PicksAndBansS7.GameId)=cnt",
    where: whereParts.join(" AND "),
    joinOn: "PicksAndBansS7.GameId=ScoreboardGames.GameId",
    groupBy: "PicksAndBansS7.GameId",
    limit: 1,
  });
  // countDrafts używamy tylko jako wskaźnik kompletności w UI — join do
  // MatchScheduleGame nie jest tu potrzebny.
  // Cargo z group by zwraca jeden wiersz per GameId; lepiej policzyć length.
  // Dla dokładnego countu zrób oddzielne paginated query.
  return rows.length;
}

// --- Normalizacja ---------------------------------------------------------

function normalize(row: CargoRow): RawDraft {
  const gameId = toStr(row.GameId);
  const bans = (n: 1 | 2): string[] => {
    const out: string[] = [];
    for (let i = 1; i <= 5; i++) {
      const v = toStr(row[`t${n}b${i}`]);
      if (v) out.push(v);
    }
    return out;
  };
  const pick = (k: string): string | null => toStr(row[k]) || null;

  // Konwersja Leaguepedia (Team1=Blue, Team2=Red) na nasze nazwy:
  // B1=t1p1, R1=t2p1, R2=t2p2, B2=t1p2, B3=t1p3, R3=t2p3,
  // B4=t1p4, B5=t1p5, R4=t2p4, R5=t2p5
  const blueTeam = toStr(row.Team1) || null;
  const redTeam = toStr(row.Team2) || null;

  // firstPickSide — porównanie MatchScheduleGame.FirstPick z Blue/Red nazwą.
  // Pre-2026 LP zwraca puste FirstPick → null (analyzer traktuje jako 'blue').
  const msgBlue = toStr(row.MsgBlue);
  const msgRed = toStr(row.MsgRed);
  const msgFirstPick = toStr(row.MsgFirstPick);
  let firstPickSide: "blue" | "red" | null = null;
  if (msgFirstPick) {
    if (msgFirstPick === msgBlue) firstPickSide = "blue";
    else if (msgFirstPick === msgRed) firstPickSide = "red";
    // Inny przypadek (rebrand drużyny między MSG a ScoreboardGames?) — null.
  }

  return {
    matchId: gameId,
    patch: toStr(row.Patch) || null,
    league: toStr(row.Tournament),
    gameDate: parseUtc(row.DateTime),
    blueTeam,
    redTeam,
    blueBans: bans(1),
    redBans: bans(2),
    b1Pick: pick("t1p1"),
    r1Pick: pick("t2p1"),
    r2Pick: pick("t2p2"),
    b2Pick: pick("t1p2"),
    b3Pick: pick("t1p3"),
    r3Pick: pick("t2p3"),
    b4Pick: pick("t1p4"),
    b5Pick: pick("t1p5"),
    r4Pick: pick("t2p4"),
    r5Pick: pick("t2p5"),
    firstPickSide,
    winner: toStr(row.Winner) || null,
  };
}

function parseUtc(value: unknown): Date | null {
  const s = toStr(value);
  if (!s) return null;
  // Leaguepedia DateTime_UTC format: "2025-01-15 18:00:00"
  const iso = s.includes("T") ? s : s.replace(" ", "T") + "Z";
  const d = new Date(iso);
  return Number.isFinite(d.getTime()) ? d : null;
}

function hasAnyPick(d: RawDraft): boolean {
  return [
    d.b1Pick, d.r1Pick, d.r2Pick, d.b2Pick, d.b3Pick,
    d.r3Pick, d.b4Pick, d.b5Pick, d.r4Pick, d.r5Pick,
  ].some((p) => p);
}
