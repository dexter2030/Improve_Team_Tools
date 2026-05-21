/**
 * Cargo fetch TournamentPlayers — rostery per liga z metadanymi gracza
 * (join z Players).
 *
 * TournamentPlayers ma jeden wiersz per (gracz, drużyna, turniej) — coach
 * widzi nie tylko aktualny roster ale i ostatnie tournament w którym
 * gracz brał udział.
 *
 * Dla MVP: dedupe po (overviewPage, league), zachowujemy NAJNOWSZY
 * tournament (po DateStart).
 */

import {
  cargoPaginated,
  cargoEscape,
  toStr,
  type CargoRow,
} from "./cargo";
import { moreSpecific } from "./leagues";

export interface RawTournamentPlayer {
  overviewPage: string;
  league: string;
  id: string | null;
  team: string | null;
  role: string | null;
  country: string | null;
  nationalityPrimary: string | null;
  lastTournament: string | null;
  lastTournamentStart: Date | null;
}

const FIELDS = [
  "TournamentPlayers.OverviewPage=OverviewPage",
  "TournamentPlayers.Team=Team",
  "TournamentPlayers.Role=Role",
  "TournamentPlayers.Tournament=Tournament",
  "Tournaments.DateStart=DateStart",
  "Players.ID=ID",
  "Players.Country=Country",
  "Players.NationalityPrimary=NationalityPrimary",
].join(",");

/**
 * Pobiera rostery z danej ligi (Tournament LIKE %league% z wykluczeniem
 * bardziej szczegółowych nazw). Zwraca już zdedupowane wiersze
 * (overviewPage, league) — najnowszy tournament wygrywa.
 */
export async function fetchTournamentPlayers(
  league: string,
  maxRows = 50000
): Promise<RawTournamentPlayer[]> {
  const escaped = cargoEscape(league);
  const exclusions = moreSpecific(league)
    .map((m) => `Tournaments.Name NOT LIKE '%${cargoEscape(m)}%'`)
    .join(" AND ");

  const whereParts = [
    `Tournaments.Name LIKE '%${escaped}%'`,
    ...(exclusions ? [exclusions] : []),
  ];

  const rows = await cargoPaginated(
    {
      tables: "TournamentPlayers,Tournaments,Players",
      fields: FIELDS,
      where: whereParts.join(" AND "),
      joinOn:
        "TournamentPlayers.Tournament=Tournaments.OverviewPage," +
        "TournamentPlayers.OverviewPage=Players.OverviewPage",
      orderBy: "Tournaments.DateStart DESC",
    },
    maxRows
  );

  // Dedupe (overviewPage, league) — pierwszy raz spotkany (najnowszy
  // bo sortowane DESC).
  const seen = new Set<string>();
  const out: RawTournamentPlayer[] = [];
  for (const row of rows) {
    const page = toStr(row.OverviewPage);
    if (!page) continue;
    const key = `${page}|${league}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(normalize(row, league));
  }
  return out;
}

function normalize(row: CargoRow, league: string): RawTournamentPlayer {
  const start = toStr(row.DateStart);
  let dt: Date | null = null;
  if (start) {
    const d = new Date(start.includes("T") ? start : `${start}T00:00:00Z`);
    if (Number.isFinite(d.getTime())) dt = d;
  }
  return {
    overviewPage: toStr(row.OverviewPage),
    league,
    id: toStr(row.ID) || null,
    team: toStr(row.Team) || null,
    role: toStr(row.Role) || null,
    country: toStr(row.Country) || null,
    nationalityPrimary: toStr(row.NationalityPrimary) || null,
    lastTournament: toStr(row.Tournament) || null,
    lastTournamentStart: dt,
  };
}
