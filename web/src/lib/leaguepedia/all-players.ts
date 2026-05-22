/**
 * Cargo fetch dla globalnej tabeli Players (~30k+ wierszy).
 * Paginujemy do `maxRows`; default 50k bezpiecznie nad faktyczny rozmiar.
 */

import { cargoPaginated, toStr, toBool, type CargoRow } from "./cargo";

export interface RawLpPlayer {
  overviewPage: string;
  id: string | null;
  team: string | null;
  role: string | null;
  country: string | null;
  residency: string | null;
  nationalityPrimary: string | null;
  lolpros: string | null;
  isRetired: boolean;
}

export async function fetchAllPlayers(maxRows = 50000): Promise<RawLpPlayer[]> {
  const rows = await cargoPaginated(
    {
      tables: "Players",
      fields:
        "Players.OverviewPage=OverviewPage,Players.ID=ID,Players.Team=Team," +
        "Players.Role=Role,Players.Country=Country,Players.Residency=Residency," +
        "Players.NationalityPrimary=NationalityPrimary,Players.Lolpros=Lolpros," +
        "Players.IsRetired=IsRetired",
      orderBy: "Players.OverviewPage ASC",
    },
    maxRows
  );
  return rows.map(normalize).filter((p) => p.overviewPage);
}

function normalize(row: CargoRow): RawLpPlayer {
  return {
    overviewPage: toStr(row.OverviewPage),
    id: toStr(row.ID) || null,
    team: toStr(row.Team) || null,
    role: toStr(row.Role) || null,
    country: toStr(row.Country) || null,
    residency: toStr(row.Residency) || null,
    nationalityPrimary: toStr(row.NationalityPrimary) || null,
    lolpros: toStr(row.Lolpros) || null,
    isRetired: toBool(row.IsRetired),
  };
}
