import Link from "next/link";
import { notFound } from "next/navigation";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { ALL_LEAGUES } from "@/lib/leaguepedia/leagues";
import { getLeagueRanking } from "@/lib/ranking";
import { distinctStatYears } from "@/lib/ranking/stats-repository";
import { sortRankedPlayers } from "@/lib/ranking/sort";
import { parseYearRange, yearRangeLabel } from "@/lib/ranking/year-range";
import { RankingSortHeader } from "../sort-header";
import { RankingFilters } from "../ranking-filters";
import { SplitTrend } from "../split-trend";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ name: string }>;
  searchParams: Promise<{ role?: string; sort?: string; from?: string; to?: string }>;
}

export default async function LeagueRanking({ params, searchParams }: Props) {
  const { name } = await params;
  const league = decodeURIComponent(name);
  if (!ALL_LEAGUES.includes(league)) notFound();

  const sp = await searchParams;
  const roleFilter = sp.role || undefined;
  const sort = sp.sort || "rating:desc";
  const range = parseYearRange(sp.from, sp.to);

  const [all, years] = await Promise.all([
    getLeagueRanking(league, range),
    distinctStatYears(league),
  ]);
  const roles = [...new Set(all.map((p) => p.role).filter(Boolean))].sort() as string[];
  const filtered = roleFilter ? all.filter((p) => p.role === roleFilter) : all;
  const rows = sortRankedPlayers(filtered, sort);

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/ranking"
          className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> Wszystkie ligi
        </Link>
        <h2 className="text-2xl font-semibold tracking-tight">
          Ranking — {league}
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          {rows.length} graczy · ocena i potencjał ({yearRangeLabel(range)},
          Leaguepedia). Ocena = forma vs kohorta (rola × liga × rok × split);
          potencjał = trajektoria + wiek + dominacja + awans.
        </p>
      </div>

      {years.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Brak danych dla tej ligi. Wróć do{" "}
            <Link href="/ranking" className="text-primary hover:underline">
              listy lig
            </Link>{" "}
            i kliknij „Pobierz”.
          </CardContent>
        </Card>
      ) : (
        <>
          <RankingFilters
            roles={roles}
            years={years}
            role={roleFilter}
            from={range.yearFrom}
            to={range.yearTo}
            sort={sort}
          />

          {rows.length === 0 ? (
            <Card>
              <CardContent className="py-10 text-center text-sm text-muted-foreground">
                Brak graczy dla wybranych filtrów. Poszerz zakres lat lub zmień
                rolę.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="p-0">
                <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-10">#</TableHead>
                    <TableHead>
                      <RankingSortHeader column="player" label="Gracz" />
                    </TableHead>
                    <TableHead>
                      <RankingSortHeader column="role" label="Rola" />
                    </TableHead>
                    <TableHead className="text-right">
                      <RankingSortHeader column="age" label="Wiek" align="right" />
                    </TableHead>
                    <TableHead className="text-right">
                      <RankingSortHeader column="games" label="Gier" align="right" />
                    </TableHead>
                    <TableHead className="text-right">
                      <RankingSortHeader column="rating" label="Ocena" align="right" />
                    </TableHead>
                    <TableHead className="text-right">
                      <RankingSortHeader
                        column="potential"
                        label="Potencjał"
                        align="right"
                      />
                    </TableHead>
                    <TableHead>Forma split-do-splitu</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((p, i) => (
                    <TableRow key={p.overviewPage}>
                      <TableCell className="text-muted-foreground tabular-nums">
                        {i + 1}
                      </TableCell>
                      <TableCell className="font-medium">
                        <a
                          href={`https://lol.fandom.com/wiki/${encodeURIComponent(
                            p.overviewPage.replace(/ /g, "_")
                          )}`}
                          target="_blank"
                          rel="noreferrer"
                          className="hover:underline"
                        >
                          {p.overviewPage}
                        </a>
                        {p.lowSample && (
                          <Badge variant="outline" className="ml-2 text-[10px]">
                            mała próba
                          </Badge>
                        )}
                      </TableCell>
                      <TableCell>{p.role ?? "—"}</TableCell>
                      <TableCell className="text-right tabular-nums">
                        {p.age ?? "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {p.games}
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <span className="tabular-nums font-semibold">
                          {p.rating}
                        </span>
                        <Badge variant="secondary" className="ml-2">
                          {p.tier}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right whitespace-nowrap">
                        <span className="tabular-nums font-semibold">
                          {p.potential}
                        </span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {p.potentialLabel}
                        </span>
                      </TableCell>
                      <TableCell>
                        <SplitTrend perSplit={p.perSplit} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
