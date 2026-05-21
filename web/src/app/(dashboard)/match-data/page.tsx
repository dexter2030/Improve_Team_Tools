/**
 * Match Data — pełen szeroki widok draftów (wszystkie 20 sloty pick&ban
 * w kolejności draftu). Czyste czytanie z drafts, brak sync — pobieranie
 * jest w Database.
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
import { Filters } from "../draft-analyzer/filters";
import { ChampionIcon } from "@/components/champion-cell";
import {
  countAllDrafts,
  distinctPatches,
  getAllDrafts,
} from "@/lib/drafts/repository";
import {
  filterByLeagues,
  filterByPatches,
} from "@/lib/drafts/analyzer";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{
    league?: string;
    patch?: string;
    team?: string;
  }>;
}

export default async function MatchDataPage({ searchParams }: Props) {
  const sp = await searchParams;
  const leagues = (sp.league ?? "").split(",").filter(Boolean);
  const patches = (sp.patch ?? "").split(",").filter(Boolean);
  const teamQuery = (sp.team ?? "").trim().toLowerCase();

  const [total, allPatches] = await Promise.all([
    countAllDrafts(),
    distinctPatches(),
  ]);

  if (total === 0) {
    return (
      <div className="space-y-6">
        <Header />
        <Alert>
          <Info className="h-4 w-4" />
          <AlertTitle>Brak draftów</AlertTitle>
          <AlertDescription>
            Wczytaj drafty w zakładce <strong>Database</strong>, aby zobaczyć
            pełny widok pick &amp; ban.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  const all = await getAllDrafts();
  let filtered = all;
  if (leagues.length > 0) filtered = filterByLeagues(filtered, leagues);
  if (patches.length > 0) filtered = filterByPatches(filtered, patches);
  if (teamQuery) {
    filtered = filtered.filter(
      (d) =>
        (d.blueTeam && d.blueTeam.toLowerCase().includes(teamQuery)) ||
        (d.redTeam && d.redTeam.toLowerCase().includes(teamQuery))
    );
  }

  return (
    <div className="space-y-6">
      <Header />

      <Card>
        <CardHeader>
          <CardTitle>Filtry</CardTitle>
          <CardDescription>
            {filtered.length === total
              ? `Wszystkie ${total} draftów.`
              : `${filtered.length} z ${total} draftów.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Filters patches={allPatches} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Drafty</CardTitle>
          <CardDescription>
            Pełna sekwencja pick &amp; ban w kolejności draftu (B1/R1/R2/B2/B3/R3/B4/B5/R4/R5).
            Pierwsze {Math.min(100, filtered.length)} wyników.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b bg-muted/40">
              <tr className="text-left text-muted-foreground">
                <th className="px-2 py-2 font-medium">Patch</th>
                <th className="px-2 py-2 font-medium">Data</th>
                <th className="px-2 py-2 font-medium">Liga</th>
                <th className="px-2 py-2 font-medium text-right">Blue</th>
                <th className="px-2 py-2 font-medium">vs</th>
                <th className="px-2 py-2 font-medium">Red</th>
                <th className="px-2 py-2 font-medium text-center">Bany fazy 1</th>
                <th className="px-2 py-2 font-medium text-center">Picki fazy 1</th>
                <th className="px-2 py-2 font-medium text-center">Bany fazy 2</th>
                <th className="px-2 py-2 font-medium text-center">Picki fazy 2</th>
                <th className="px-2 py-2 font-medium">Wygrana</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 100).map((d) => (
                <tr key={d.matchId} className="border-b hover:bg-muted/30">
                  <td className="px-2 py-2 font-mono">{d.patch ?? "—"}</td>
                  <td className="px-2 py-2 text-muted-foreground whitespace-nowrap">
                    {d.gameDate
                      ? new Date(d.gameDate).toLocaleDateString("pl-PL", {
                          year: "2-digit",
                          month: "2-digit",
                          day: "2-digit",
                        })
                      : "—"}
                  </td>
                  <td className="px-2 py-2 max-w-[160px] truncate text-muted-foreground">
                    {d.league}
                  </td>
                  <td className="px-2 py-2 text-right font-medium">{d.blueTeam ?? "—"}</td>
                  <td className="px-2 py-2 text-muted-foreground">vs</td>
                  <td className="px-2 py-2 font-medium">{d.redTeam ?? "—"}</td>
                  <td className="px-2 py-2">
                    <BanRow blue={d.blueBans.slice(0, 3)} red={d.redBans.slice(0, 3)} />
                  </td>
                  <td className="px-2 py-2">
                    <Phase1Picks d={d} />
                  </td>
                  <td className="px-2 py-2">
                    <BanRow blue={d.blueBans.slice(3, 5)} red={d.redBans.slice(3, 5)} />
                  </td>
                  <td className="px-2 py-2">
                    <Phase2Picks d={d} />
                  </td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    {renderWinner(d.winner, d.blueTeam, d.redTeam)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

function BanRow({ blue, red }: { blue: string[]; red: string[] }) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex gap-0.5">
        {blue.map((c, i) => (
          <ChampionIcon key={`b${i}`} name={c} size={18} />
        ))}
      </div>
      <span className="text-muted-foreground text-[10px]">/</span>
      <div className="flex gap-0.5">
        {red.map((c, i) => (
          <ChampionIcon key={`r${i}`} name={c} size={18} />
        ))}
      </div>
    </div>
  );
}

/**
 * Faza 1 picks w kolejności draftu: B1, R1, R2, B2, B3, R3.
 * Strony naprzemiennie, dlatego oznaczamy kolorem (border).
 */
function Phase1Picks({ d }: { d: { b1Pick: string | null; r1Pick: string | null; r2Pick: string | null; b2Pick: string | null; b3Pick: string | null; r3Pick: string | null } }) {
  const seq: Array<{ name: string | null; side: "b" | "r" }> = [
    { name: d.b1Pick, side: "b" },
    { name: d.r1Pick, side: "r" },
    { name: d.r2Pick, side: "r" },
    { name: d.b2Pick, side: "b" },
    { name: d.b3Pick, side: "b" },
    { name: d.r3Pick, side: "r" },
  ];
  return <PickStrip picks={seq} />;
}

function Phase2Picks({ d }: { d: { b4Pick: string | null; b5Pick: string | null; r4Pick: string | null; r5Pick: string | null } }) {
  const seq: Array<{ name: string | null; side: "b" | "r" }> = [
    { name: d.b4Pick, side: "b" },
    { name: d.b5Pick, side: "b" },
    { name: d.r4Pick, side: "r" },
    { name: d.r5Pick, side: "r" },
  ];
  return <PickStrip picks={seq} />;
}

function PickStrip({ picks }: { picks: Array<{ name: string | null; side: "b" | "r" }> }) {
  return (
    <div className="flex gap-0.5">
      {picks.map((p, i) => (
        <div
          key={i}
          className={`border-2 rounded ${
            p.side === "b"
              ? "border-blue-500/60"
              : "border-rose-500/60"
          }`}
        >
          <ChampionIcon name={p.name} size={20} />
        </div>
      ))}
    </div>
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

function Header() {
  return (
    <div>
      <h2 className="text-2xl font-semibold tracking-tight">Match Data</h2>
      <p className="text-sm text-muted-foreground mt-1">
        Pełen widok pick &amp; ban — wszystkie 20 slotów w kolejności draftu.
        Filtry zmieniają URL — możesz udostępniać widoki.
      </p>
    </div>
  );
}
