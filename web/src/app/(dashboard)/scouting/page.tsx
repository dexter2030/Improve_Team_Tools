/**
 * Scouting List — pełna lista zawodników z DB.
 * Server Component: fetch profilLister po SSR, brak loading state.
 */

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
import { StatusBadge } from "@/components/status-badge";
import { listProfiles } from "@/lib/profiles/repository";
import type { ResolutionState, Role } from "@/lib/db/schema";
import { UserPlus } from "lucide-react";
import { ScoutingFilters } from "./filters";

export const dynamic = "force-dynamic"; // żadne stale cache — chcemy świeże po Server Action revalidate

interface Props {
  searchParams: Promise<{
    search?: string;
    role?: string;
    status?: string;
  }>;
}

export default async function ScoutingListPage({ searchParams }: Props) {
  const sp = await searchParams;
  const search = (sp.search ?? "").trim().toLowerCase();
  const role = sp.role as Role | undefined;
  const status = sp.status as ResolutionState | undefined;

  const all = await listProfiles();
  const profiles = all.filter((p) => {
    if (role && p.role !== role) return false;
    if (status && p.resolutionState !== status) return false;
    if (search) {
      const hay = [
        p.displayName,
        p.nationality,
        p.proplay?.leaguepediaLink,
        p.proplay?.currentTeam,
        ...p.soloq.map((s) => s.riotId),
      ]
        .filter(Boolean)
        .map((s) => String(s).toLowerCase());
      if (!hay.some((h) => h.includes(search))) return false;
    }
    return true;
  });

  const counts: Record<ResolutionState, number> = {
    resolved: 0,
    partial: 0,
    failed: 0,
    unresolved: 0,
  };
  for (const p of all) counts[p.resolutionState]++; // metryki na pełnej liście, nie po filtrach
  const hasFilter = !!(search || role || status);

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight">Tracked players</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Lista obserwowanych zawodników z rozwiązanymi tożsamościami SoloQ i pro-play.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link
            href="/scouting/import"
            className={buttonVariants({ variant: "outline" })}
          >
            📥 Bulk import
          </Link>
          <Link href="/scouting/add" className={buttonVariants()}>
            <UserPlus className="h-4 w-4 mr-2" />
            Dodaj gracza
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Total" value={all.length} />
        <StatCard label="Resolved" value={counts.resolved} />
        <StatCard label="Partial" value={counts.partial} />
        <StatCard label="Failed / Unresolved" value={counts.failed + counts.unresolved} />
      </div>

      {all.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Filtry</CardTitle>
            <CardDescription>
              {hasFilter
                ? `${profiles.length} z ${all.length} pasuje do filtrów.`
                : "Wszystkie profile pokazane."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ScoutingFilters />
          </CardContent>
        </Card>
      )}

      {all.length === 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Pusto</CardTitle>
            <CardDescription>
              Nie ma jeszcze żadnych zawodników. Dodaj pierwszego w zakładce <strong>Add Player</strong>.
            </CardDescription>
          </CardHeader>
        </Card>
      ) : profiles.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Żaden profil nie spełnia filtrów.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nazwa</TableHead>
                  <TableHead>Rola</TableHead>
                  <TableHead>Wiek</TableHead>
                  <TableHead>Kraj</TableHead>
                  <TableHead>op.gg</TableHead>
                  <TableHead>Top level</TableHead>
                  <TableHead>Leaguepedia</TableHead>
                  <TableHead>Team</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {profiles.map((p) => {
                  const nResolved = p.soloq.filter((s) => s.puuid !== null).length;
                  const levels = p.soloq
                    .map((s) => s.summonerLevel)
                    .filter((l): l is number => l !== null);
                  const topLevel = levels.length ? Math.max(...levels) : null;
                  return (
                    <TableRow key={p.profileId}>
                      <TableCell>
                        <Link
                          href={`/scouting/${p.profileId}`}
                          className="text-primary hover:underline font-medium"
                        >
                          {p.displayName}
                        </Link>
                      </TableCell>
                      <TableCell>{p.role}</TableCell>
                      <TableCell>{p.age ?? "—"}</TableCell>
                      <TableCell>{p.nationality ?? "—"}</TableCell>
                      <TableCell>
                        {p.soloq.length ? `${nResolved}/${p.soloq.length}` : "—"}
                      </TableCell>
                      <TableCell>{topLevel ?? "—"}</TableCell>
                      <TableCell className="max-w-[180px] truncate">
                        {p.proplay?.leaguepediaLink ?? "—"}
                      </TableCell>
                      <TableCell>{p.proplay?.currentTeam ?? "—"}</TableCell>
                      <TableCell>
                        <StatusBadge state={p.resolutionState} />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
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
