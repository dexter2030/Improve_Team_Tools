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
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import {
  countPlayers,
  distinctCountries,
  distinctRoles,
  getSyncState,
  listPlayersPaginated,
  type SortColumn,
  type SortDir,
} from "@/lib/players/repository";
import { SyncBar } from "./sync-bar";
import { PlayersFilters } from "./filters";
import { Pagination } from "./pagination";
import { SortHeader } from "./sort-header";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{
    role?: string;
    playerRolesOnly?: string;
    country?: string;
    search?: string;
    hideRetired?: string;
    sort?: string;
    page?: string;
  }>;
}

export default async function PlayersDataPage({ searchParams }: Props) {
  const sp = await searchParams;
  const role = sp.role || undefined;
  const playerRolesOnly = sp.playerRolesOnly === "1";
  const country = sp.country || undefined;
  const search = sp.search || undefined;
  const hideRetired = sp.hideRetired === "1";
  const page = sp.page ? Math.max(1, Number(sp.page) || 1) : 1;
  const [sortColRaw, sortDirRaw] = (sp.sort ?? "").split(":");
  const sortBy = (
    ["id", "role", "team", "country", "isRetired"] as SortColumn[]
  ).includes(sortColRaw as SortColumn)
    ? (sortColRaw as SortColumn)
    : "id";
  const sortDir: SortDir = sortDirRaw === "desc" ? "desc" : "asc";

  const [total, syncState, roles, countries] = await Promise.all([
    countPlayers(),
    getSyncState(),
    distinctRoles(),
    distinctCountries(),
  ]);

  const pageSize = 100;
  const paginated =
    total > 0
      ? await listPlayersPaginated({
          role,
          playerRolesOnly,
          country,
          search,
          hideRetired,
          page,
          pageSize,
          sortBy,
          sortDir,
        })
      : { rows: [], total: 0, page: 1, pageSize, totalPages: 1 };
  const players = paginated.rows;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Players Data</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Global Leaguepedia player table (~30k rows). First fetch takes a moment;
            refresh updates rosters after transfers.
          </p>
        </div>
        <Link
          href="/players-data/league"
          className={buttonVariants({ variant: "outline" })}
        >
          🏆 Per-league mode →
        </Link>
      </div>

      <SyncBar count={total} lastFetched={syncState?.lastFetched ?? null} />

      {total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Filters</CardTitle>
            <CardDescription>
              {paginated.total.toLocaleString("en-US")} players match filters
              (of {total.toLocaleString("en-US")} in DB). Click a column header to sort.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <PlayersFilters roles={roles} countries={countries} />
          </CardContent>
        </Card>
      )}

      {total === 0 ? null : players.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            No players match the filters.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <SortHeader column="id" label="Name" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="role" label="Role" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="team" label="Team" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="country" label="Country" />
                  </TableHead>
                  <TableHead>Residency</TableHead>
                  <TableHead>
                    <SortHeader column="isRetired" label="Status" />
                  </TableHead>
                  <TableHead>Leaguepedia</TableHead>
                  <TableHead>lolpros</TableHead>
                  <TableHead className="text-right">Scouting</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {players.map((p) => {
                  const leaguepediaUrl = `https://lol.fandom.com/wiki/${encodeURIComponent(
                    p.overviewPage.replace(/ /g, "_")
                  )}`;
                  // Cargo's Players.Lolpros field is already a full URL
                  // (e.g. https://lolpros.gg/player/curator), not a slug —
                  // don't prefix it. Slug-only fallback kept defensively.
                  const lolprosUrl = p.lolpros
                    ? p.lolpros.startsWith("http")
                      ? p.lolpros
                      : `https://lolpros.gg/player/${p.lolpros}`
                    : null;
                  const lolprosLabel = p.lolpros
                    ? p.lolpros
                        .replace(/^https?:\/\/lolpros\.gg\/player\//, "")
                        .replace(/\/$/, "")
                    : null;
                  const scoutingRoles = ["Top", "Jungle", "Mid", "Bot", "Support"];
                  const canScout = !!p.role && scoutingRoles.includes(p.role);
                  const addParams = new URLSearchParams();
                  if (p.id) addParams.set("displayName", p.id);
                  if (canScout && p.role) addParams.set("role", p.role);
                  if (p.country) addParams.set("nationality", p.country);
                  addParams.set("leaguepediaUrl", leaguepediaUrl);
                  if (lolprosUrl) addParams.set("lolprosUrl", lolprosUrl);
                  return (
                    <TableRow key={p.overviewPage}>
                      <TableCell className="font-medium">
                        {p.id ?? "—"}
                      </TableCell>
                      <TableCell>{p.role ?? "—"}</TableCell>
                      <TableCell>{p.team ?? "—"}</TableCell>
                      <TableCell>{p.country ?? "—"}</TableCell>
                      <TableCell>{p.residency ?? "—"}</TableCell>
                      <TableCell>
                        {p.isRetired ? (
                          <Badge variant="secondary">retired</Badge>
                        ) : (
                          <Badge>active</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <a
                          href={leaguepediaUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary hover:underline text-xs"
                        >
                          {p.overviewPage} ↗
                        </a>
                      </TableCell>
                      <TableCell>
                        {lolprosUrl ? (
                          <a
                            href={lolprosUrl}
                            target="_blank"
                            rel="noreferrer"
                            className="text-primary hover:underline text-xs"
                          >
                            {lolprosLabel} ↗
                          </a>
                        ) : (
                          <span className="text-xs text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <Link
                          href={`/scouting/add?${addParams.toString()}`}
                          className={buttonVariants({ variant: "outline", size: "xs" })}
                          title={
                            canScout
                              ? "Add to scouting list (prefilled)"
                              : "Role not supported — pick it in the form"
                          }
                        >
                          + Scouting
                        </Link>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
            <Pagination
              page={paginated.page}
              totalPages={paginated.totalPages}
              total={paginated.total}
              pageSize={paginated.pageSize}
            />
          </CardContent>
        </Card>
      )}
    </div>
  );
}
