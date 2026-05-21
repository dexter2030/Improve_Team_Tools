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
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Players Data</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Globalna baza graczy z Leaguepedia (~30k wpisów). Pobieranie zajmuje
          chwilę — następne odświeżanie aktualizuje rostery po transferach.
        </p>
      </div>

      <SyncBar count={total} lastFetched={syncState?.lastFetched ?? null} />

      {total > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Filtry</CardTitle>
            <CardDescription>
              {paginated.total.toLocaleString("pl-PL")} graczy spełnia filtry
              (z {total.toLocaleString("pl-PL")} w bazie). Kliknij nagłówek
              kolumny żeby posortować.
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
            Brak graczy spełniających filtry.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>
                    <SortHeader column="id" label="Nick" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="role" label="Rola" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="team" label="Drużyna" />
                  </TableHead>
                  <TableHead>
                    <SortHeader column="country" label="Kraj" />
                  </TableHead>
                  <TableHead>Rezydencja</TableHead>
                  <TableHead>
                    <SortHeader column="isRetired" label="Status" />
                  </TableHead>
                  <TableHead>Leaguepedia</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {players.map((p) => (
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
                        href={`https://lol.fandom.com/wiki/${encodeURIComponent(
                          p.overviewPage.replace(/ /g, "_")
                        )}`}
                        target="_blank"
                        rel="noreferrer"
                        className="text-primary hover:underline text-xs"
                      >
                        {p.overviewPage} ↗
                      </a>
                    </TableCell>
                  </TableRow>
                ))}
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
