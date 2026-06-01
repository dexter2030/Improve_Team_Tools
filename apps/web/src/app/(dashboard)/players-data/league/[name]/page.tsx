import Link from "next/link";
import { notFound } from "next/navigation";
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
import { ArrowLeft } from "lucide-react";
import {
  distinctRolesInLeague,
  listLeaguePlayers,
} from "@/lib/players/league-repository";
import { ALL_LEAGUES } from "@/lib/leaguepedia/leagues";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ name: string }>;
  searchParams: Promise<{ role?: string; search?: string }>;
}

export default async function LeagueDetail({ params, searchParams }: Props) {
  const { name } = await params;
  const league = decodeURIComponent(name);
  if (!ALL_LEAGUES.includes(league)) notFound();

  const sp = await searchParams;
  const role = sp.role || undefined;
  const search = sp.search?.trim() || undefined;

  const [players, roles] = await Promise.all([
    listLeaguePlayers(league, { role, search }),
    distinctRolesInLeague(league),
  ]);

  // Grupowanie po team dla łatwego skanowania.
  const byTeam = new Map<string, typeof players>();
  for (const p of players) {
    const t = p.team ?? "Free agents";
    const arr = byTeam.get(t) ?? [];
    arr.push(p);
    byTeam.set(t, arr);
  }

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/players-data/league"
          className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
        >
          <ArrowLeft className="h-4 w-4 mr-1" /> All leagues
        </Link>
        <h2 className="text-2xl font-semibold tracking-tight">{league}</h2>
        <p className="text-sm text-muted-foreground mt-1">
          {players.length} players in DB · {byTeam.size} teams.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-3" action="" method="get">
            <input
              type="search"
              name="search"
              defaultValue={search ?? ""}
              placeholder="Search (name, team)..."
              className="border rounded-md px-3 py-2 text-sm"
            />
            <select
              name="role"
              defaultValue={role ?? ""}
              className="border rounded-md px-3 py-2 text-sm bg-background"
            >
              <option value="">All roles</option>
              {roles.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
            <button
              type="submit"
              className={buttonVariants({ variant: "default", size: "default" })}
            >
              Apply
            </button>
          </form>
        </CardContent>
      </Card>

      {[...byTeam.entries()]
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([team, ps]) => (
          <Card key={team}>
            <CardHeader>
              <CardTitle>{team}</CardTitle>
              <CardDescription>{ps.length} players</CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Name</TableHead>
                    <TableHead>Role</TableHead>
                    <TableHead>Country</TableHead>
                    <TableHead>Last tournament</TableHead>
                    <TableHead>Leaguepedia</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {ps.map((p) => (
                    <TableRow key={p.overviewPage}>
                      <TableCell className="font-medium">{p.id ?? "—"}</TableCell>
                      <TableCell>{p.role ?? "—"}</TableCell>
                      <TableCell>{p.country ?? "—"}</TableCell>
                      <TableCell className="text-xs text-muted-foreground max-w-[200px] truncate">
                        {p.lastTournament ?? "—"}
                      </TableCell>
                      <TableCell>
                        <a
                          href={`https://lol.fandom.com/wiki/${encodeURIComponent(p.overviewPage.replace(/ /g, "_"))}`}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary hover:underline text-xs"
                        >
                          ↗
                        </a>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        ))}
    </div>
  );
}
