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
  listPlayers,
} from "@/lib/players/repository";
import { SyncBar } from "./sync-bar";
import { PlayersFilters } from "./filters";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{
    role?: string;
    country?: string;
    search?: string;
    hideRetired?: string;
  }>;
}

export default async function PlayersDataPage({ searchParams }: Props) {
  const sp = await searchParams;
  const role = sp.role || undefined;
  const country = sp.country || undefined;
  const search = sp.search || undefined;
  const hideRetired = sp.hideRetired === "1";

  const [total, syncState, roles, countries] = await Promise.all([
    countPlayers(),
    getSyncState(),
    distinctRoles(),
    distinctCountries(),
  ]);

  const players =
    total > 0
      ? await listPlayers({ role, country, search, hideRetired, limit: 500 })
      : [];

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
              Pokazuję pierwsze 500 wyników. Zaw  ęź filtry żeby znaleźć
              konkretnego gracza.
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
                  <TableHead>Nick</TableHead>
                  <TableHead>Rola</TableHead>
                  <TableHead>Drużyna</TableHead>
                  <TableHead>Kraj</TableHead>
                  <TableHead>Rezydencja</TableHead>
                  <TableHead>Status</TableHead>
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
          </CardContent>
        </Card>
      )}
    </div>
  );
}
