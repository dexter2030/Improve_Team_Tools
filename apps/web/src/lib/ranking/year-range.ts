/**
 * Parsowanie i opis zakresu lat z query (?from=&to=) — czyste helpery
 * współdzielone przez widoki rankingu (liga i narodowość).
 */

import { RANKING_SINCE_YEARS } from "./weights";

export interface YearRange {
  yearFrom?: number;
  yearTo?: number;
}

/** from/to z query → liczby; odwrócony zakres (from > to) prostujemy swapem. */
export function parseYearRange(from?: string, to?: string): YearRange {
  const f = toYear(from);
  const t = toYear(to);
  if (f !== undefined && t !== undefined && f > t) {
    return { yearFrom: t, yearTo: f };
  }
  return { yearFrom: f, yearTo: t };
}

function toYear(v?: string): number | undefined {
  if (!v) return undefined;
  const n = Number.parseInt(v, 10);
  return Number.isInteger(n) ? n : undefined;
}

/** Czytelny opis okna lat do nagłówka strony. */
export function yearRangeLabel({ yearFrom, yearTo }: YearRange): string {
  if (yearFrom !== undefined && yearTo !== undefined) {
    return yearFrom === yearTo
      ? `sezon ${yearFrom}`
      : `sezony ${yearFrom}–${yearTo}`;
  }
  if (yearFrom !== undefined) return `sezony od ${yearFrom}`;
  if (yearTo !== undefined) return `sezony do ${yearTo}`;
  return `ostatnie ${RANKING_SINCE_YEARS} sezony`;
}
