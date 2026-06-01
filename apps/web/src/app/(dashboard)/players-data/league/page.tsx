import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { buttonVariants } from "@/components/ui/button";
import { Globe } from "lucide-react";
import { LEAGUE_GROUPS } from "@/lib/leaguepedia/leagues";
import {
  leagueCounts,
  getLeagueSyncStates,
} from "@/lib/players/league-repository";
import { LeagueSyncButton } from "./sync-button";

export const dynamic = "force-dynamic";

export default async function LeaguePlayersIndex() {
  const [counts, sync] = await Promise.all([
    leagueCounts(),
    getLeagueSyncStates(),
  ]);
  const syncMap = new Map(sync.map((s) => [s.league, s]));

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">
            Players Data — per league
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            Rosters from Leaguepedia TournamentPlayers. Each league synced
            independently — pick only the ones you scout.
          </p>
        </div>
        <Link
          href="/players-data"
          className={buttonVariants({ variant: "outline" })}
        >
          <Globe className="h-4 w-4 mr-2" />
          Back to global
        </Link>
      </div>

      <Section
        title="Tier 1"
        leagues={LEAGUE_GROUPS.tier1}
        counts={counts}
        syncMap={syncMap}
      />
      <Section
        title="ERL — D1"
        leagues={LEAGUE_GROUPS.erlD1}
        counts={counts}
        syncMap={syncMap}
      />
      <Section
        title="ERL — D2"
        leagues={LEAGUE_GROUPS.erlD2}
        counts={counts}
        syncMap={syncMap}
      />
    </div>
  );
}

function Section({
  title,
  leagues,
  counts,
  syncMap,
}: {
  title: string;
  leagues: readonly string[];
  counts: Record<string, number>;
  syncMap: Map<string, { lastFetched: Date | null }>;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>
          Click a league to see rosters. Sync before first entry.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>League</TableHead>
              <TableHead className="text-right">Players in DB</TableHead>
              <TableHead>Last fetch</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {leagues.map((lg) => {
              const n = counts[lg] ?? 0;
              const last = syncMap.get(lg)?.lastFetched;
              return (
                <TableRow key={lg}>
                  <TableCell className="font-medium">
                    {n > 0 ? (
                      <Link
                        href={`/players-data/league/${encodeURIComponent(lg)}`}
                        className="text-primary hover:underline"
                      >
                        {lg}
                      </Link>
                    ) : (
                      lg
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{n}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">
                    {last ? new Date(last).toLocaleString("en-US") : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <LeagueSyncButton league={lg} hasData={n > 0} />
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
