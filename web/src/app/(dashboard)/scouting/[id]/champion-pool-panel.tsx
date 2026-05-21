/**
 * Champion pool z Leaguepedia ScoreboardPlayers — per-champion stats
 * w pro grach. Wymaga zweryfikowanego pro-play linku.
 */

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ChampionCell } from "@/components/champion-cell";
import { getLeaguepediaClient } from "@/lib/leaguepedia";
import { aggregateChampionStats } from "@/lib/profiles/champion-stats";
import type { ProPlayIdentity } from "@/lib/profiles";

export async function ChampionPoolPanel({
  proplay,
}: {
  proplay: ProPlayIdentity | null;
}) {
  if (!proplay || !proplay.leaguepediaLink) {
    return (
      <p className="text-sm text-muted-foreground">
        Brak rozwiązanej tożsamości pro-play — champion pool niedostępny.
      </p>
    );
  }

  try {
    const client = getLeaguepediaClient();
    const rows = await client.getPlayerScoreboard(proplay.leaguepediaLink);
    if (rows.length === 0) {
      return (
        <p className="text-sm text-muted-foreground">
          Brak gier pro tego gracza na Leaguepedia.
        </p>
      );
    }
    const stats = aggregateChampionStats(rows);
    return (
      <div className="space-y-2">
        <p className="text-xs text-muted-foreground">
          {rows.length} gier · {stats.length} championów (top 15)
        </p>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Champion</TableHead>
              <TableHead className="text-right">G</TableHead>
              <TableHead className="text-right">W-L</TableHead>
              <TableHead className="text-right">WR</TableHead>
              <TableHead className="text-right">K</TableHead>
              <TableHead className="text-right">D</TableHead>
              <TableHead className="text-right">A</TableHead>
              <TableHead className="text-right">KDA</TableHead>
              <TableHead className="text-right">CS</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {stats.slice(0, 15).map((s) => (
              <TableRow key={s.champion}>
                <TableCell>
                  <ChampionCell name={s.champion} size={20} />
                </TableCell>
                <TableCell className="text-right tabular-nums">{s.games}</TableCell>
                <TableCell className="text-right tabular-nums text-xs text-muted-foreground">
                  {s.wins}-{s.losses}
                </TableCell>
                <TableCell
                  className={`text-right tabular-nums font-medium ${winColor(s.winRate)}`}
                >
                  {(s.winRate * 100).toFixed(0)}%
                </TableCell>
                <TableCell className="text-right tabular-nums text-xs">{s.avgKills}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{s.avgDeaths}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{s.avgAssists}</TableCell>
                <TableCell className="text-right tabular-nums font-medium">{s.kda}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">{s.avgCs}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return (
      <p className="text-sm text-amber-700 dark:text-amber-400">
        Nie udało się pobrać champion pool: {msg}
      </p>
    );
  }
}

function winColor(wr: number): string {
  if (wr >= 0.6) return "text-emerald-700 dark:text-emerald-400";
  if (wr <= 0.4) return "text-rose-700 dark:text-rose-400";
  return "text-foreground";
}
