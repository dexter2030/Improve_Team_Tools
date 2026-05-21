/**
 * Draft Analyzer — czyste transformacje, bez IO.
 *
 * Port draft_analyzer/analyzer.py. Picki dopasowywane pozycyjnie
 * (b1Pick, r1Pick, ...). Bany — jako pula faz (1: bany 1-3, 2: bany 4-5),
 * traktowane jako set: wymaga obecności, kolejność nieważna.
 */

import type { Draft } from "@/lib/db/schema";
import { moreSpecific } from "@/lib/leaguepedia/leagues";

export const PICK_KEYS = [
  "b1Pick", "r1Pick", "r2Pick", "b2Pick", "b3Pick",
  "r3Pick", "b4Pick", "b5Pick", "r4Pick", "r5Pick",
] as const;

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

export function searchDrafts(drafts: Draft[], p: DraftPattern): Draft[] {
  if (isPatternEmpty(p)) return [];

  return drafts.filter((d) => {
    // Blue picks pozycyjnie
    for (let i = 0; i < 5; i++) {
      const wanted = p.bluePicks[i];
      if (!wanted) continue;
      const actual = bluePickAt(d, i);
      if (actual !== wanted) return false;
    }
    // Red picks
    for (let i = 0; i < 5; i++) {
      const wanted = p.redPicks[i];
      if (!wanted) continue;
      const actual = redPickAt(d, i);
      if (actual !== wanted) return false;
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
   */
  groups: Record<string, SuggestionEntry[]>;
}

/**
 * Dla każdej kategorii (pick na pozycji, bany faz) zwraca top championów
 * w pasujących draftach, pomijając tych już wpisanych w pattern.
 */
export function suggestAll(
  drafts: Draft[],
  pattern: DraftPattern,
  topN = 10
): SuggestAllResult {
  const matches = searchDrafts(drafts, pattern);
  if (matches.length === 0) return { totalMatches: 0, groups: {} };

  const groups: Record<string, SuggestionEntry[]> = {};

  for (let i = 0; i < 5; i++) {
    const used = new Set(pattern.bluePicks.filter(Boolean) as string[]);
    if (pattern.bluePicks[i]) continue;
    groups[`bp${i}`] = top(
      matches.map((d) => bluePickAt(d, i)),
      matches.length,
      used,
      topN
    );
  }
  for (let i = 0; i < 5; i++) {
    const used = new Set(pattern.redPicks.filter(Boolean) as string[]);
    if (pattern.redPicks[i]) continue;
    groups[`rp${i}`] = top(
      matches.map((d) => redPickAt(d, i)),
      matches.length,
      used,
      topN
    );
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
