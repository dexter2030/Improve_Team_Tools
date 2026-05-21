/**
 * Draft search — pełna siatka pick&ban + lista pasujących draftów.
 * URL state: każdy slot to osobny param (b1..b5, r1..r5,
 * phase1Bans = comma list, phase2Bans = comma list).
 */

import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { buttonVariants } from "@/components/ui/button";
import { Info, ArrowLeft } from "lucide-react";
import { getAllDrafts } from "@/lib/drafts/repository";
import {
  searchDrafts,
  suggestAll,
  isPatternEmpty,
  type DraftPattern,
} from "@/lib/drafts/analyzer";
import { allChampionsMeta } from "@/lib/drafts/champion-icons";
import { ChampionIcon } from "@/components/champion-cell";
import { DraftBoard } from "./draft-board";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<Record<string, string | undefined>>;
}

export default async function DraftSearchPage({ searchParams }: Props) {
  const sp = await searchParams;
  const pattern = parsePattern(sp);

  const [allDraftsList, champions] = await Promise.all([
    safeGetDrafts(),
    allChampionsMeta(),
  ]);

  const iconByName: Record<string, string> = {};
  for (const c of champions) iconByName[c.name] = c.iconUrl;

  const matches = searchDrafts(allDraftsList, pattern);
  const suggestions = !isPatternEmpty(pattern)
    ? suggestAll(allDraftsList, pattern, 6)
    : null;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <Link
            href="/draft-analyzer"
            className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
          >
            <ArrowLeft className="h-4 w-4 mr-1" />
            Z powrotem do analyzera
          </Link>
          <h2 className="text-2xl font-semibold tracking-tight">Wyszukiwarka draftów</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Wybierz championów na konkretnych pozycjach i / lub w bany faz —
            znajdziemy wszystkie pro drafty pasujące do wzorca.
          </p>
        </div>
      </div>

      {allDraftsList.length === 0 && (
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Brak draftów</AlertTitle>
          <AlertDescription>
            Wczytaj ligi w <strong>Database</strong>.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Draft Board</CardTitle>
          <CardDescription>
            Klikaj sloty żeby ustawić championy. Kolejność wierszy odpowiada
            kolejności wyborów w prawdziwym pro drafcie (rose = bany,
            emerald = picki).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DraftBoard champions={champions} iconByName={iconByName} />
        </CardContent>
      </Card>

      {!isPatternEmpty(pattern) && (
        <>
          {suggestions && suggestions.totalMatches > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Sugestie dla pustych slotów</CardTitle>
                <CardDescription>
                  Top championów które trafiały w te sloty w pasujących{" "}
                  <strong>{suggestions.totalMatches}</strong> draftach.
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(suggestions.groups).map(([key, entries]) => {
                    if (entries.length === 0) return null;
                    return (
                      <div key={key} className="space-y-2">
                        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                          {groupLabel(key)}
                        </div>
                        <ul className="space-y-1">
                          {entries.slice(0, 6).map((e) => (
                            <li
                              key={e.champion}
                              className="flex items-center gap-2 text-xs"
                            >
                              <ChampionIcon name={e.champion} size={20} />
                              <span>{e.champion}</span>
                              <span className="ml-auto text-muted-foreground tabular-nums">
                                {e.pct.toFixed(0)}%
                              </span>
                            </li>
                          ))}
                        </ul>
                      </div>
                    );
                  })}
                </div>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Pasujące drafty</CardTitle>
              <CardDescription>
                {matches.length === 0
                  ? "Brak pasujących — spróbuj zaw  ęź lub rozluźnij filtry."
                  : `Znaleziono ${matches.length}. Pokazuję pierwsze 30.`}
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0 overflow-x-auto">
              {matches.length > 0 && (
                <table className="w-full text-xs">
                  <thead className="border-b bg-muted/40">
                    <tr className="text-left text-muted-foreground">
                      <th className="px-3 py-2">Patch</th>
                      <th className="px-3 py-2">Liga</th>
                      <th className="px-3 py-2">Blue</th>
                      <th className="px-3 py-2">Red</th>
                      <th className="px-3 py-2">Picks (B / R)</th>
                      <th className="px-3 py-2">Wygrana</th>
                    </tr>
                  </thead>
                  <tbody>
                    {matches.slice(0, 30).map((d) => (
                      <tr key={d.matchId} className="border-b hover:bg-muted/30">
                        <td className="px-3 py-2 font-mono">{d.patch ?? "—"}</td>
                        <td className="px-3 py-2 max-w-[180px] truncate text-muted-foreground">
                          {d.league}
                        </td>
                        <td className="px-3 py-2">{d.blueTeam ?? "—"}</td>
                        <td className="px-3 py-2">{d.redTeam ?? "—"}</td>
                        <td className="px-3 py-2">
                          <div className="flex items-center gap-1">
                            {[d.b1Pick, d.b2Pick, d.b3Pick, d.b4Pick, d.b5Pick].map(
                              (c, i) => (
                                <ChampionIcon key={`b${i}`} name={c} size={18} />
                              )
                            )}
                            <span className="text-muted-foreground mx-1">/</span>
                            {[d.r1Pick, d.r2Pick, d.r3Pick, d.r4Pick, d.r5Pick].map(
                              (c, i) => (
                                <ChampionIcon key={`r${i}`} name={c} size={18} />
                              )
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">
                          {renderWinner(d.winner, d.blueTeam, d.redTeam)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
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

function groupLabel(key: string): string {
  const i = Number(key.slice(2));
  if (key.startsWith("bp")) return `Blue P${i + 1}`;
  if (key.startsWith("rp")) return `Red P${i + 1}`;
  if (key === "phase1_bans") return "Bany fazy 1";
  if (key === "phase2_bans") return "Bany fazy 2";
  return key;
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
