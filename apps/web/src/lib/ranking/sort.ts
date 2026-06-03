/**
 * Sortowanie zrankowanych graczy po kolumnie tabeli — współdzielone przez widok
 * rankingu ligi i rankingu narodowości. Czyste (bez DB/sieci).
 */

import type { RankedPlayer } from "./score";

/** Klucz sortowania w formacie `kolumna:kierunek` (np. "rating:desc"). */
export function sortRankedPlayers(
  rows: RankedPlayer[],
  sort: string
): RankedPlayer[] {
  const [col, dir] = sort.split(":");
  const sign = dir === "asc" ? 1 : -1;
  const val = (p: RankedPlayer): number | string => {
    switch (col) {
      case "player":
        return p.overviewPage.toLowerCase();
      case "league":
        return p.league;
      case "role":
        return p.role ?? "";
      case "age":
        return p.age ?? -1;
      case "games":
        return p.games;
      case "potential":
        return p.potential;
      case "rating":
      default:
        return p.rating;
    }
  };
  return [...rows].sort((a, b) => {
    const va = val(a);
    const vb = val(b);
    if (typeof va === "string" || typeof vb === "string") {
      return sign * String(va).localeCompare(String(vb));
    }
    return sign * (va - vb);
  });
}
