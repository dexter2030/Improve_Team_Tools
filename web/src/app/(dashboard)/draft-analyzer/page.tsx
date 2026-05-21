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
} from "@/lib/drafts/analyzer";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ league?: string; patch?: string }>;
}

export default async function DraftAnalyzerPage({ searchParams }: Props) {
  const sp = await searchParams;
  const leagues = (sp.league ?? "").split(",").filter(Boolean);
  const patches = (sp.patch ?? "").split(",").filter(Boolean);

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
          <AlertTitle>Brak draftów w bazie</AlertTitle>
          <AlertDescription>
            Najpierw wczytaj drafty w zakładce <strong>Database</strong>. Po
            synchronizacji wróć tutaj — statystyki i wyszukiwarka draftów
            zaczną pokazywać dane.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  // MVP: fetch wszystkie i filtruj w pamięci. Optymalizacja (server-side
  // SQL filter) gdy zbiór będzie ciężki.
  const all = await getAllDrafts();
  let filtered = all;
  if (leagues.length > 0) filtered = filterByLeagues(filtered, leagues);
  if (patches.length > 0) filtered = filterByPatches(filtered, patches);

  const firstPicks = firstPickStats(filtered, 10);
  const bans = phase1BanStats(filtered, 10);

  return (
    <div className="space-y-6">
      <Header />

      <Card>
        <CardHeader>
          <CardTitle>Filtry</CardTitle>
          <CardDescription>
            {filtered.length === total
              ? `Wszystkie ${total} draftów w bazie.`
              : `${filtered.length} z ${total} draftów spełnia filtry.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Filters patches={allPatches} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Top first picks (B1)</CardTitle>
            <CardDescription>
              Najczęstszy pierwszy pick (Blue side B1) wśród filtrowanych draftów.
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
              Najczęstsze bany fazy 1 (pierwsze 3 bany per strona).
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
          <CardTitle>Ostatnie drafty</CardTitle>
          <CardDescription>
            50 najnowszych draftów spełniających filtry.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0 overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="border-b">
              <tr className="text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Patch</th>
                <th className="px-3 py-2 font-medium">Liga</th>
                <th className="px-3 py-2 font-medium">Blue</th>
                <th className="px-3 py-2 font-medium">vs</th>
                <th className="px-3 py-2 font-medium">Red</th>
                <th className="px-3 py-2 font-medium">Pickset (Blue / Red)</th>
                <th className="px-3 py-2 font-medium">Wygrana</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 50).map((d) => (
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
                      {[d.b1Pick, d.b2Pick, d.b3Pick, d.b4Pick, d.b5Pick].map((c, i) => (
                        <ChampionIcon key={`b${i}`} name={c} size={22} />
                      ))}
                      <span className="text-muted-foreground mx-1">/</span>
                      {[d.r1Pick, d.r2Pick, d.r3Pick, d.r4Pick, d.r5Pick].map((c, i) => (
                        <ChampionIcon key={`r${i}`} name={c} size={22} />
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2">{renderWinner(d.winner, d.blueTeam, d.redTeam)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}

/**
 * Cargo zwraca Winner jako "1" (Team1=Blue) lub "2" (Team2=Red), nie
 * jako nazwa drużyny. Mapujemy obie konwencje.
 */
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
      <h2 className="text-2xl font-semibold tracking-tight">Draft Analyzer</h2>
      <p className="text-sm text-muted-foreground mt-1">
        Statystyki pick &amp; ban na danych z Leaguepedia. Filtry zmieniają URL,
        co pozwala udostępniać widoki.
      </p>
    </div>
  );
}

async function ChampionList({
  entries,
}: {
  entries: { champion: string; count: number; pct: number }[];
}) {
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">Brak danych.</p>;
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
