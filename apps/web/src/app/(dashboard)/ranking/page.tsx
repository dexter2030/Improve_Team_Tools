import Link from "next/link";
import { Flag, ArrowRight } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
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
  statsPlayerCounts,
  getStatsSyncStates,
} from "@/lib/ranking/stats-repository";
import { RankingSyncButton } from "./sync-button";
import { RankingSchemaNotice } from "./schema-notice";
import { isSchemaBehindError } from "@/lib/ranking/schema-error";

export const dynamic = "force-dynamic";

export default async function RankingIndex() {
  let counts: Record<string, number> = {};
  let sync: Awaited<ReturnType<typeof getStatsSyncStates>> = [];
  let schemaBehind = false;
  try {
    [counts, sync] = await Promise.all([
      statsPlayerCounts(),
      getStatsSyncStates(),
    ]);
  } catch (e) {
    if (!isSchemaBehindError(e)) throw e;
    schemaBehind = true;
  }
  const syncMap = new Map(sync.map((s) => [s.league, s]));

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Ranking graczy</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Ocena i potencjał zawodników liczone z ich statystyk meczowych
          (Leaguepedia). Każda liga synchronizowana osobno — zsynchronizuj, potem
          otwórz jej ranking.
        </p>
      </div>

      {schemaBehind ? (
        <RankingSchemaNotice />
      ) : (
        <>
          <Card>
            <CardContent className="flex flex-wrap items-center justify-between gap-4 py-4">
              <div className="flex items-start gap-3">
                <Flag className="h-5 w-5 mt-0.5 text-primary shrink-0" />
                <div>
                  <p className="font-medium">Ranking Polaków</p>
                  <p className="text-sm text-muted-foreground">
                    Wszyscy gracze polskiej narodowości ze zsynchronizowanych lig
                    w jednym rankingu — niezależnie od ligi.
                  </p>
                </div>
              </div>
              <Link
                href="/ranking/nationality/Poland"
                className={buttonVariants({ variant: "default", size: "sm" })}
              >
                Otwórz <ArrowRight className="h-4 w-4 ml-1" />
              </Link>
            </CardContent>
          </Card>

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
        </>
      )}
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
          Kliknij ligę, by zobaczyć ranking. Najpierw zsynchronizuj dane.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Liga</TableHead>
              <TableHead className="text-right">Graczy</TableHead>
              <TableHead>Ostatni sync</TableHead>
              <TableHead className="text-right">Akcja</TableHead>
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
                        href={`/ranking/${encodeURIComponent(lg)}`}
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
                    {last ? new Date(last).toLocaleString("pl-PL") : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <RankingSyncButton league={lg} hasData={n > 0} />
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
