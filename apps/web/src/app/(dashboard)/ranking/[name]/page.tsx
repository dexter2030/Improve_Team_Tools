import Link from "next/link";
import { notFound } from "next/navigation";
import {
  Card,
  CardContent,
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
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { ALL_LEAGUES } from "@/lib/leaguepedia/leagues";
import { RANKING_SINCE_YEARS } from "@/lib/ranking/weights";
import { getLeagueRanking, type RankedPlayer } from "@/lib/ranking";
import { RankingSortHeader } from "../sort-header";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ name: string }>;
  searchParams: Promise<{ role?: string; sort?: string }>;
}

export default async function LeagueRanking({ params, searchParams }: Props) {
  const { name } = await params;
  const league = decodeURIComponent(name);
  if (!ALL_LEAGUES.includes(league)) notFound();

  const sp = await searchParams;
  const roleFilter = sp.role || undefined;
  const sort = sp.sort || "rating:desc";

  const all = await getLeagueRanking(league);
  const roles = [...new Set(all.map((p) => p.role).filter(Boolean))].sort() as string[];
  const filtered = roleFilter ? all.filter((p) => p.role === roleFilter) : all;
  const rows = sortRows(filtered, sort);

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
          {rows.length} graczy · ocena i potencjał z ostatnich {RANKING_SINCE_YEARS}{" "}
          sezonów (Leaguepedia). Ocena = forma vs kohorta (rola × liga × rok);
          potencjał = trajektoria + wiek + dominacja + awans.
        </p>
      </div>

      {all.length === 0 ? (
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
          <Card>
            <CardHeader>
              <CardTitle>Filtry</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="grid gap-3 md:grid-cols-3" method="get">
                <select
                  name="role"
                  defaultValue={roleFilter ?? ""}
                  className="border rounded-md px-3 py-2 text-sm bg-background"
                >
                  <option value="">Wszystkie role</option>
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
                {sort !== "rating:desc" && (
                  <input type="hidden" name="sort" value={sort} />
                )}
                <button
                  type="submit"
                  className={buttonVariants({ variant: "default" })}
                >
                  Zastosuj
                </button>
              </form>
            </CardContent>
          </Card>

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
                    <TableHead>Forma rok-do-roku</TableHead>
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
                        <YearTrend perYear={p.perYear} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

function YearTrend({ perYear }: { perYear: RankedPlayer["perYear"] }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-xs">
      {perYear.map((y) => (
        <span
          key={`${y.year}-${y.league}`}
          title={`${y.league} (${y.games} gier)`}
          className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 tabular-nums"
        >
          <span className="text-muted-foreground">
            &apos;{String(y.year).slice(2)}
          </span>
          <span
            className={
              y.yearZ === null
                ? "text-muted-foreground"
                : y.yearZ >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
            }
          >
            {y.yearZ === null
              ? "·"
              : (y.yearZ >= 0 ? "+" : "") + y.yearZ.toFixed(1)}
          </span>
        </span>
      ))}
    </div>
  );
}

function sortRows(rows: RankedPlayer[], sort: string): RankedPlayer[] {
  const [col, dir] = sort.split(":");
  const sign = dir === "asc" ? 1 : -1;
  const val = (p: RankedPlayer): number | string => {
    switch (col) {
      case "player":
        return p.overviewPage.toLowerCase();
      case "role":
        return p.role ?? "";
      case "age":
        return p.age ?? -1;
      case "games":
        return p.games;
      case "potential":
        return p.potential;
      case "rating":
      default:
        return p.rating;
    }
  };
  return [...rows].sort((a, b) => {
    const va = val(a);
    const vb = val(b);
    if (typeof va === "string" || typeof vb === "string") {
      return sign * String(va).localeCompare(String(vb));
    }
    return sign * (va - vb);
  });
}
