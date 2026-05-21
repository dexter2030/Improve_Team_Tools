import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { LEAGUE_GROUPS } from "@/lib/leaguepedia/leagues";
import {
  countAllDrafts,
  draftCountsByLeague,
  getLeagueSyncAll,
} from "@/lib/drafts/repository";
import { SyncButton } from "./sync-button";

export const dynamic = "force-dynamic";

export default async function DatabasePage() {
  const [total, byLeague, syncState] = await Promise.all([
    countAllDrafts(),
    draftCountsByLeague(),
    getLeagueSyncAll(),
  ]);

  const syncMap = new Map(syncState.map((s) => [s.league, s]));
  const leaguesWithData = Object.keys(byLeague).length;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Database</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Synchronizacja draftów z Leaguepedia. Pobieranie jest idempotentne
          (powtórzenia są deduplikowane przez matchId).
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Drafty w bazie" value={total} />
        <StatCard label="Ligi z danymi" value={leaguesWithData} />
        <StatCard
          label="Wszystkie wspierane ligi"
          value={
            LEAGUE_GROUPS.tier1.length +
            LEAGUE_GROUPS.erlD1.length +
            LEAGUE_GROUPS.erlD2.length
          }
        />
      </div>

      <Separator />

      <LeagueSection
        title="Tier 1 — major leagues + international"
        description="LEC, LCK, LPL, LCS oraz MSI/Worlds/First Stand."
        leagues={LEAGUE_GROUPS.tier1}
        countsByLeague={countsByPrefix(byLeague)}
        syncMap={syncMap}
      />

      <LeagueSection
        title="ERL — pierwsze dywizje"
        description="Główne europejskie ligi regionalne."
        leagues={LEAGUE_GROUPS.erlD1}
        countsByLeague={countsByPrefix(byLeague)}
        syncMap={syncMap}
      />

      <LeagueSection
        title="ERL — drugie dywizje"
        description="Akademiki i dywizje rozwojowe."
        leagues={LEAGUE_GROUPS.erlD2}
        countsByLeague={countsByPrefix(byLeague)}
        syncMap={syncMap}
      />
    </div>
  );
}

function LeagueSection({
  title,
  description,
  leagues,
  countsByLeague,
  syncMap,
}: {
  title: string;
  description: string;
  leagues: readonly string[];
  countsByLeague: (lg: string) => number;
  syncMap: Map<string, { lastFetched: Date | null }>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Liga</TableHead>
              <TableHead className="text-right">W bazie</TableHead>
              <TableHead>Ostatnie wczytanie</TableHead>
              <TableHead className="text-right">Akcja</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {leagues.map((lg) => {
              const count = countsByLeague(lg);
              const last = syncMap.get(lg)?.lastFetched;
              return (
                <TableRow key={lg}>
                  <TableCell className="font-medium">{lg}</TableCell>
                  <TableCell className="text-right">{count}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {last ? new Date(last).toLocaleString("pl-PL") : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <SyncButton league={lg} hasData={count > 0} />
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}

/**
 * Zwraca funkcję która liczy ile draftów ma liga `lg`, sumując wszystkie
 * Tournament names z DB które zaczynają się od `lg` (Leaguepedia robi
 * "LEC 2025 Summer" itd., więc fuzzy match).
 */
function countsByPrefix(byLeague: Record<string, number>) {
  return (lg: string): number => {
    const lower = lg.toLowerCase();
    let total = 0;
    for (const [tournament, n] of Object.entries(byLeague)) {
      if (tournament.toLowerCase().includes(lower)) total += n;
    }
    return total;
  };
}
