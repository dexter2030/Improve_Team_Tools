/**
 * Draft Analyzer — czyste transformacje, bez IO.
 *
 * Picki w prawdziwym drafcie są częściowo pickowane jednocześnie:
 *   - B2/B3 → para (cały blue P2/P3 idzie naraz)
 *   - B4/B5 → para
 *   - R1/R2 → para
 *   - R4/R5 → para
 *   - B1, R3 → standalone
 * Czyli przy wyszukiwaniu kolejność w parze NIE MA znaczenia — jeśli user
 * wpisze R1=Azir i R2=Caitlyn, dopasujemy też drafty gdzie r1Pick=Caitlyn
 * i r2Pick=Azir. Bany — zawsze pula faz.
 */

import type { Draft } from "@/lib/db/schema";
import { moreSpecific } from "@/lib/leaguepedia/leagues";

export const PICK_KEYS = [
  "b1Pick", "r1Pick", "r2Pick", "b2Pick", "b3Pick",
  "r3Pick", "b4Pick", "b5Pick", "r4Pick", "r5Pick",
] as const;

/** Indeksy pozycji które są pickowane jednocześnie (po stronie blue/red). */
const BLUE_PAIRS: ReadonlyArray<readonly [number, number]> = [
  [1, 2], // B2 + B3
  [3, 4], // B4 + B5
];
const RED_PAIRS: ReadonlyArray<readonly [number, number]> = [
  [0, 1], // R1 + R2
  [3, 4], // R4 + R5
];

/** Lookup: indeks → indeks pary (lub null jeśli standalone). */
function pairFor(
  i: number,
  pairs: ReadonlyArray<readonly [number, number]>
): number | null {
  for (const [a, b] of pairs) {
    if (i === a) return b;
    if (i === b) return a;
  }
  return null;
}

export interface DraftPattern {
  /** Blue picks po pozycji (0..4 = B1, B2, B3, B4, B5). null = wildcard. */
  bluePicks: (string | null)[];
  /** Red picks (0..4 = R1, R2, R3, R4, R5). null = wildcard. */
  redPicks: (string | null)[];
  /** Bany fazy 1 (1-3) — pula z obu stron, nieuporządkowana. */
  phase1Bans: string[];
  /** Bany fazy 2 (4-5). */
  phase2Bans: string[];
}

export function isPatternEmpty(p: DraftPattern): boolean {
  return (
    p.bluePicks.every((v) => !v) &&
    p.redPicks.every((v) => !v) &&
    p.phase1Bans.length === 0 &&
    p.phase2Bans.length === 0
  );
}

/**
 * Sprawdza czy zestaw wymaganych championów na pozycjach (i, partnerI)
 * pasuje do draftu — wymaga obecności jako MULTISET (kolejność nieważna).
 */
function pairMatches(
  wantedAtI: string | null,
  wantedAtJ: string | null,
  actualAtI: string | null,
  actualAtJ: string | null
): boolean {
  // Brak wymagań — pasuje
  if (!wantedAtI && !wantedAtJ) return true;
  // Oba wymagane — multiset równość
  if (wantedAtI && wantedAtJ) {
    const wanted = [wantedAtI, wantedAtJ].sort();
    const actual = [actualAtI ?? "", actualAtJ ?? ""].sort();
    return wanted[0] === actual[0] && wanted[1] === actual[1];
  }
  // Tylko jedno wymagane — musi być w którymś slocie
  const w = wantedAtI || wantedAtJ;
  return actualAtI === w || actualAtJ === w;
}

export function searchDrafts(drafts: Draft[], p: DraftPattern): Draft[] {
  if (isPatternEmpty(p)) return [];

  return drafts.filter((d) => {
    // Blue picks — z uwzględnieniem par.
    const blueChecked = new Set<number>();
    for (let i = 0; i < 5; i++) {
      if (blueChecked.has(i)) continue;
      const partner = pairFor(i, BLUE_PAIRS);
      if (partner === null) {
        // Standalone (B1)
        const wanted = p.bluePicks[i];
        if (wanted && bluePickAt(d, i) !== wanted) return false;
        blueChecked.add(i);
      } else {
        if (
          !pairMatches(
            p.bluePicks[i],
            p.bluePicks[partner],
            bluePickAt(d, i),
            bluePickAt(d, partner)
          )
        )
          return false;
        blueChecked.add(i);
        blueChecked.add(partner);
      }
    }
    // Red picks
    const redChecked = new Set<number>();
    for (let i = 0; i < 5; i++) {
      if (redChecked.has(i)) continue;
      const partner = pairFor(i, RED_PAIRS);
      if (partner === null) {
        const wanted = p.redPicks[i];
        if (wanted && redPickAt(d, i) !== wanted) return false;
        redChecked.add(i);
      } else {
        if (
          !pairMatches(
            p.redPicks[i],
            p.redPicks[partner],
            redPickAt(d, i),
            redPickAt(d, partner)
          )
        )
          return false;
        redChecked.add(i);
        redChecked.add(partner);
      }
    }
    // Bany — pula faz
    const phase1 = new Set([
      ...d.blueBans.slice(0, 3),
      ...d.redBans.slice(0, 3),
    ]);
    for (const b of p.phase1Bans) {
      if (!phase1.has(b)) return false;
    }
    const phase2 = new Set([
      ...d.blueBans.slice(3, 5),
      ...d.redBans.slice(3, 5),
    ]);
    for (const b of p.phase2Bans) {
      if (!phase2.has(b)) return false;
    }
    return true;
  });
}

export interface SuggestionEntry {
  champion: string;
  count: number;
  pct: number;
}

export interface SuggestAllResult {
  totalMatches: number;
  /**
   * Klucze: bp0..bp4, rp0..rp4, phase1_bans, phase2_bans.
   * Każdy → top-listy championów dla pustych slotów.
   * Dla pozycji w parze, sugestie są wspólne (top z obu pozycji łącznie).
   */
  groups: Record<string, SuggestionEntry[]>;
}

/**
 * Top championów per slot/grupa. Dla pozycji w parze sugestie są
 * obliczane na pool obu pozycji łącznie.
 */
export function suggestAll(
  drafts: Draft[],
  pattern: DraftPattern,
  topN = 10
): SuggestAllResult {
  const matches = searchDrafts(drafts, pattern);
  if (matches.length === 0) return { totalMatches: 0, groups: {} };

  const groups: Record<string, SuggestionEntry[]> = {};

  // Blue picks per pozycja — z uwzględnieniem par.
  for (let i = 0; i < 5; i++) {
    if (pattern.bluePicks[i]) continue; // już wypełniony, brak sugestii
    const partner = pairFor(i, BLUE_PAIRS);
    const used = new Set(pattern.bluePicks.filter(Boolean) as string[]);
    let pool: (string | null)[];
    if (partner === null) {
      pool = matches.map((d) => bluePickAt(d, i));
    } else {
      // Pool z obu pozycji w parze
      pool = matches.flatMap((d) => [
        bluePickAt(d, i),
        bluePickAt(d, partner),
      ]);
    }
    groups[`bp${i}`] = top(pool, matches.length, used, topN);
  }

  // Red picks — analogicznie.
  for (let i = 0; i < 5; i++) {
    if (pattern.redPicks[i]) continue;
    const partner = pairFor(i, RED_PAIRS);
    const used = new Set(pattern.redPicks.filter(Boolean) as string[]);
    let pool: (string | null)[];
    if (partner === null) {
      pool = matches.map((d) => redPickAt(d, i));
    } else {
      pool = matches.flatMap((d) => [
        redPickAt(d, i),
        redPickAt(d, partner),
      ]);
    }
    groups[`rp${i}`] = top(pool, matches.length, used, topN);
  }

  const phase1Used = new Set(pattern.phase1Bans);
  groups.phase1_bans = top(
    matches.flatMap((d) => [...d.blueBans.slice(0, 3), ...d.redBans.slice(0, 3)]),
    matches.length,
    phase1Used,
    topN
  );

  const phase2Used = new Set(pattern.phase2Bans);
  groups.phase2_bans = top(
    matches.flatMap((d) => [...d.blueBans.slice(3, 5), ...d.redBans.slice(3, 5)]),
    matches.length,
    phase2Used,
    topN
  );

  return { totalMatches: matches.length, groups };
}

export interface SideBanStats {
  blue: SuggestionEntry[];
  red: SuggestionEntry[];
  total: number;
}

/** Top bany fazy 1 osobno per strona. */
export function phase1BanStats(drafts: Draft[], topN = 10): SideBanStats {
  const total = drafts.length;
  const blueBans = drafts.flatMap((d) => d.blueBans.slice(0, 3));
  const redBans = drafts.flatMap((d) => d.redBans.slice(0, 3));
  return {
    blue: top(blueBans, total, new Set(), topN),
    red: top(redBans, total, new Set(), topN),
    total,
  };
}

/** Top B1 (globalny first pick). */
export function firstPickStats(drafts: Draft[], topN = 10): SuggestionEntry[] {
  return top(
    drafts.map((d) => d.b1Pick),
    drafts.length,
    new Set(),
    topN
  );
}

/** Filtr po patchach (puste = wszystkie). */
export function filterByPatches(
  drafts: Draft[],
  allowedPatches: string[]
): Draft[] {
  if (allowedPatches.length === 0) return drafts;
  const set = new Set(allowedPatches);
  return drafts.filter((d) => d.patch && set.has(d.patch));
}

/** Filtr po lidze — substring match, wykluczając moreSpecific(). */
export function filterByLeagues(
  drafts: Draft[],
  allowedLeagues: string[]
): Draft[] {
  if (allowedLeagues.length === 0) return drafts;
  const norm = (s: string) => s.toLowerCase();
  return drafts.filter((d) => {
    const tour = norm(d.league);
    return allowedLeagues.some((lg) => {
      const want = norm(lg);
      if (!tour.includes(want)) return false;
      const exclude = moreSpecific(lg).map(norm);
      return !exclude.some((e) => tour.includes(e));
    });
  });
}

/**
 * Sort patchy numerycznie, od najnowszego. Obsługuje formaty:
 *   "9.16", "25.18", "26.09", "25.S1.3"
 * "S1" traktujemy jako liczba (S → ignore prefix). 25.S1.3 < 25.18
 * (bo 18 > 1 jako liczba po pierwszym kropce).
 */
export function sortPatchesDesc(patches: readonly string[]): string[] {
  return [...patches].sort((a, b) => {
    const ak = patchKey(a);
    const bk = patchKey(b);
    const len = Math.max(ak.length, bk.length);
    for (let i = 0; i < len; i++) {
      const av = ak[i] ?? 0;
      const bv = bk[i] ?? 0;
      if (av !== bv) return bv - av;
    }
    return 0;
  });
}

function patchKey(p: string): number[] {
  return p.split(".").map((part) => {
    const m = part.match(/^S(\d+)$/i);
    if (m) return Number(m[1]);
    const n = Number(part);
    return Number.isFinite(n) ? n : 0;
  });
}

// --- Helpers ---------------------------------------------------------------

function bluePickAt(d: Draft, i: number): string | null {
  const keys = ["b1Pick", "b2Pick", "b3Pick", "b4Pick", "b5Pick"] as const;
  return d[keys[i]];
}

function redPickAt(d: Draft, i: number): string | null {
  const keys = ["r1Pick", "r2Pick", "r3Pick", "r4Pick", "r5Pick"] as const;
  return d[keys[i]];
}

function top(
  values: (string | null | undefined)[],
  total: number,
  exclude: Set<string>,
  topN: number
): SuggestionEntry[] {
  const counts = new Map<string, number>();
  for (const v of values) {
    if (!v || exclude.has(v)) continue;
    counts.set(v, (counts.get(v) ?? 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, topN)
    .map(([champion, count]) => ({
      champion,
      count,
      pct: total === 0 ? 0 : (100 * count) / total,
    }));
}
