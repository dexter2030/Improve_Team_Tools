/**
 * Draft Analyzer — wszystko w jednym miejscu:
 *   - Filtry (presety lig + patche) — URL params: league, patch
 *   - Draft Board (klikalne sloty z sugestiami) — URL params: b1..r5, phase1Bans, phase2Bans
 *   - Top first picks / Top first-phase bans (na filtrowanych draftach)
 *   - Pasujące drafty (gdy pattern niepusty) ALBO ostatnie 50 (gdy pusty)
 *
 * Wszystkie statystyki + suggestions liczone na DRAFTACH PO FILTRACH lig/patchy,
 * więc zmiana presetu/patcha aktualizuje board sugestie + stats jednocześnie.
 */

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Info } from "lucide-react";
import { Filters } from "./filters";
import { ChampionCell, ChampionIcon } from "@/components/champion-cell";
import {
  countAllDrafts,
  distinctPatches,
  getAllDrafts,
} from "@/lib/drafts/repository";
import {
  filterByLeagues,
  filterByPatches,
  firstPickStats,
  phase1BanStats,
  searchDrafts,
  suggestAll,
  isPatternEmpty,
  type DraftPattern,
} from "@/lib/drafts/analyzer";
import { allChampionsMeta } from "@/lib/drafts/champion-icons";
import { DraftBoard } from "./draft-board";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function DraftAnalyzerPage({ searchParams }: Props) {
  const sp = await searchParams;
  const leagues = (sp.league ?? "").split(",").filter(Boolean);
  const patches = (sp.patch ?? "").split(",").filter(Boolean);
  const pattern = parsePattern(sp);

  const [total, allPatches, all, champions] = await Promise.all([
    countAllDrafts(),
    distinctPatches(),
    safeGetDrafts(),
    allChampionsMeta(),
  ]);

  const iconByName: Record<string, string> = {};
  for (const c of champions) iconByName[c.name] = c.iconUrl;

  // Apply filters lig/patchy najpierw — pozostałe operacje (suggestions,
  // matches, top stats) liczymy na tym zbiorze.
  let filtered = all;
  if (leagues.length > 0) filtered = filterByLeagues(filtered, leagues);
  if (patches.length > 0) filtered = filterByPatches(filtered, patches);

  // Suggestions na filtrowanych draftach — zmiana ligi/patcha zmienia
  // top championów per slot natychmiast.
  const suggestions = filtered.length > 0 ? suggestAll(filtered, pattern, 8) : null;
  const matches = searchDrafts(filtered, pattern);
  const firstPicks = firstPickStats(filtered, 10);
  const bans = phase1BanStats(filtered, 10);
  const hasPattern = !isPatternEmpty(pattern);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Draft Analyzer</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Pick &amp; ban stats + interactive board. Changing league preset or patch
          updates the slot suggestions live.
        </p>
      </div>

      {total === 0 && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>No drafts in DB</AlertTitle>
          <AlertDescription>
            Load drafts in the <strong>Database</strong> tab first. After sync,
            return here — stats, suggestions and search will start showing data.
          </AlertDescription>
        </Alert>
      )}

      {total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Filters</CardTitle>
            <CardDescription>
              {filtered.length === total
                ? `All ${total} drafts in DB.`
                : `${filtered.length} of ${total} drafts match league/patch filters.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Filters patches={allPatches} />
          </CardContent>
        </Card>
      )}

      {total > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Draft Board</CardTitle>
            <CardDescription>
              Click slots to build a pattern. Top 5 suggestions appear next to
              each empty slot (based on filtered drafts).
            </CardDescription>
          </CardHeader>
          <CardContent>
            <DraftBoard
              champions={champions}
              iconByName={iconByName}
              suggestions={suggestions}
            />
          </CardContent>
        </Card>
      )}

      {/* Wyniki: gdy pattern niepusty pokazujemy pasujące drafty,
          inaczej (czysta tablica) - top stats + ostatnie 50. */}
      {total > 0 && hasPattern && (
        <Card>
          <CardHeader>
            <CardTitle>Matching drafts</CardTitle>
            <CardDescription>
              {matches.length === 0
                ? "No matches — relax the pattern or change filters."
                : `Found ${matches.length}. Showing first 30.`}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 overflow-x-auto">
            {matches.length > 0 && (
              <DraftsTable drafts={matches.slice(0, 30)} />
            )}
          </CardContent>
        </Card>
      )}

      {total > 0 && !hasPattern && (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Top first picks (B1)</CardTitle>
                <CardDescription>
                  Most common first pick across filtered drafts.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <ChampionList entries={firstPicks} />
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Top first-phase bans</CardTitle>
                <CardDescription>
                  Most common phase 1 bans (first 3 bans per side).
                </CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4 sm:grid-cols-2">
                <div>
                  <div className="text-xs font-semibold mb-2 text-blue-700 dark:text-blue-400">
                    Blue side
                  </div>
                  <ChampionList entries={bans.blue} />
                </div>
                <div>
                  <div className="text-xs font-semibold mb-2 text-rose-700 dark:text-rose-400">
                    Red side
                  </div>
                  <ChampionList entries={bans.red} />
                </div>
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Recent drafts</CardTitle>
              <CardDescription>
                50 most recent drafts matching league/patch filters.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              <DraftsTable drafts={filtered.slice(0, 50)} />
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

async function safeGetDrafts() {
  try {
    return await getAllDrafts();
  } catch {
    return [];
  }
}

function parsePattern(sp: Record<string, string | undefined>): DraftPattern {
  const get = (k: string): string | null => (sp[k] || "").trim() || null;
  const list = (k: string): string[] =>
    (sp[k] || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  return {
    bluePicks: ["b1", "b2", "b3", "b4", "b5"].map(get),
    redPicks: ["r1", "r2", "r3", "r4", "r5"].map(get),
    phase1Bans: list("phase1Bans"),
    phase2Bans: list("phase2Bans"),
  };
}

interface DraftRow {
  matchId: string;
  patch: string | null;
  league: string;
  blueTeam: string | null;
  redTeam: string | null;
  winner: string | null;
  b1Pick: string | null;
  b2Pick: string | null;
  b3Pick: string | null;
  b4Pick: string | null;
  b5Pick: string | null;
  r1Pick: string | null;
  r2Pick: string | null;
  r3Pick: string | null;
  r4Pick: string | null;
  r5Pick: string | null;
}

function DraftsTable({ drafts }: { drafts: DraftRow[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="border-b bg-muted/40">
        <tr className="text-left text-muted-foreground">
          <th className="px-3 py-2 font-medium">Patch</th>
          <th className="px-3 py-2 font-medium">League</th>
          <th className="px-3 py-2 font-medium">Blue</th>
          <th className="px-3 py-2 font-medium">vs</th>
          <th className="px-3 py-2 font-medium">Red</th>
          <th className="px-3 py-2 font-medium">Pickset (Blue / Red)</th>
          <th className="px-3 py-2 font-medium">Winner</th>
        </tr>
      </thead>
      <tbody>
        {drafts.map((d) => (
          <tr key={d.matchId} className="border-b hover:bg-muted/40">
            <td className="px-3 py-2 font-mono">{d.patch ?? "—"}</td>
            <td className="px-3 py-2 text-muted-foreground max-w-[200px] truncate">
              {d.league}
            </td>
            <td className="px-3 py-2">{d.blueTeam ?? "—"}</td>
            <td className="px-3 py-2 text-muted-foreground">vs</td>
            <td className="px-3 py-2">{d.redTeam ?? "—"}</td>
            <td className="px-3 py-2">
              <div className="flex items-center gap-1">
                {[d.b1Pick, d.b2Pick, d.b3Pick, d.b4Pick, d.b5Pick].map(
                  (c, i) => (
                    <ChampionIcon key={`b${i}`} name={c} size={22} />
                  )
                )}
                <span className="text-muted-foreground mx-1">/</span>
                {[d.r1Pick, d.r2Pick, d.r3Pick, d.r4Pick, d.r5Pick].map(
                  (c, i) => (
                    <ChampionIcon key={`r${i}`} name={c} size={22} />
                  )
                )}
              </div>
            </td>
            <td className="px-3 py-2">
              {renderWinner(d.winner, d.blueTeam, d.redTeam)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function renderWinner(
  winner: string | null,
  blueTeam: string | null,
  redTeam: string | null
) {
  if (!winner) return "—";
  const isBlue = winner === "1" || winner === blueTeam;
  const isRed = winner === "2" || winner === redTeam;
  const team = isBlue ? blueTeam : isRed ? redTeam : winner;
  const className = isBlue
    ? "text-blue-700 dark:text-blue-400 font-medium"
    : isRed
      ? "text-rose-700 dark:text-rose-400 font-medium"
      : "";
  return <span className={className}>{team ?? "—"}</span>;
}

async function ChampionList({
  entries,
}: {
  entries: { champion: string; count: number; pct: number }[];
}) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">No data.</p>;
  }
  return (
    <ul className="space-y-1.5">
      {entries.map((e) => (
        <li key={e.champion} className="flex items-center gap-2">
          <ChampionCell name={e.champion} size={24} />
          <div className="ml-auto flex items-center gap-3 text-xs text-muted-foreground">
            <span className="tabular-nums">{e.count}×</span>
            <span className="tabular-nums w-12 text-right">
              {e.pct.toFixed(1)}%
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
