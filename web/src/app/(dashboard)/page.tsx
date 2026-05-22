/**
 * Home — overview metryk całego dashboardu.
 * 4 stat cards + recent profiles + sync status per moduł.
 */

import Link from "next/link";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { StatusBadge } from "@/components/status-badge";
import { Users, Database, LineChart, Trophy } from "lucide-react";
import { listProfiles } from "@/lib/profiles/repository";
import { countAllDrafts } from "@/lib/drafts/repository";
import { getLeagueSyncAll } from "@/lib/drafts/repository";
import { countPlayers, getSyncState } from "@/lib/players/repository";
import { getLeagueSyncStates } from "@/lib/players/league-repository";
import type { ResolutionState } from "@/lib/db/schema";

export const dynamic = "force-dynamic";

export default async function Home() {
  const [profiles, draftsTotal, draftLeagueSync, playersTotal, playersSync, leagueSyncStates] =
    await Promise.all([
      listProfiles(),
      countAllDrafts(),
      getLeagueSyncAll(),
      countPlayers(),
      getSyncState(),
      getLeagueSyncStates(),
    ]);

  const counts: Record<ResolutionState, number> = {
    resolved: 0,
    partial: 0,
    failed: 0,
    unresolved: 0,
  };
  for (const p of profiles) counts[p.resolutionState]++;

  const recent = profiles.slice(0, 5);
  const recentDraftSyncs = [...draftLeagueSync]
    .filter((s) => s.lastFetched)
    .sort(
      (a, b) =>
        (b.lastFetched?.getTime() ?? 0) - (a.lastFetched?.getTime() ?? 0)
    )
    .slice(0, 5);
  const recentLeaguePlayerSyncs = [...leagueSyncStates]
    .filter((s) => s.lastFetched)
    .sort(
      (a, b) =>
        (b.lastFetched?.getTime() ?? 0) - (a.lastFetched?.getTime() ?? 0)
    )
    .slice(0, 5);

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">
          Improve Team Tools
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Overview dashboard. Pick a tab on the left, or click a metric to jump to its source.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard
          icon={<Users className="h-5 w-5" />}
          label="Tracked players"
          value={profiles.length}
          href="/scouting"
          extra={
            <div className="flex gap-1 mt-2">
              {counts.resolved > 0 && <StatusBadge state="resolved" />}
              {counts.partial > 0 && <StatusBadge state="partial" />}
              {counts.failed + counts.unresolved > 0 && (
                <StatusBadge state="failed" />
              )}
            </div>
          }
        />
        <StatCard
          icon={<Trophy className="h-5 w-5" />}
          label="Drafts in DB"
          value={draftsTotal.toLocaleString("en-US")}
          href="/draft-analyzer"
          extra={
            <p className="text-xs text-muted-foreground mt-2">
              {draftLeagueSync.length > 0
                ? `${draftLeagueSync.length} leagues synced`
                : "No sync — fetch in Database"}
            </p>
          }
        />
        <StatCard
          icon={<LineChart className="h-5 w-5" />}
          label="Players (global)"
          value={playersTotal.toLocaleString("en-US")}
          href="/players-data"
          extra={
            <p className="text-xs text-muted-foreground mt-2">
              {playersSync?.lastFetched
                ? `Sync: ${new Date(playersSync.lastFetched).toLocaleDateString("en-US")}`
                : "First fetch ~1-2 min"}
            </p>
          }
        />
        <StatCard
          icon={<Database className="h-5 w-5" />}
          label="Players (per league)"
          value={leagueSyncStates.reduce((sum, s) => sum + (s.count ?? 0), 0)}
          href="/players-data/league"
          extra={
            <p className="text-xs text-muted-foreground mt-2">
              {leagueSyncStates.length > 0
                ? `${leagueSyncStates.length} leagues`
                : "Pick a league to sync"}
            </p>
          }
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recently added profiles</CardTitle>
            <CardDescription>5 most recent.</CardDescription>
          </CardHeader>
          <CardContent>
            {recent.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No profiles.{" "}
                <Link
                  href="/scouting/add"
                  className="text-primary hover:underline"
                >
                  Add the first one
                </Link>
                .
              </p>
            ) : (
              <ul className="space-y-2">
                {recent.map((p) => (
                  <li
                    key={p.profileId}
                    className="flex items-center justify-between gap-2 text-sm"
                  >
                    <Link
                      href={`/scouting/${p.profileId}`}
                      className="text-primary hover:underline font-medium"
                    >
                      {p.displayName}
                    </Link>
                    <div className="flex items-center gap-2 text-xs text-muted-foreground">
                      <span>{p.role}</span>
                      <StatusBadge state={p.resolutionState} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Recent syncs</CardTitle>
            <CardDescription>Drafts + Players (per league).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                Drafts
              </div>
              {recentDraftSyncs.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No syncs.{" "}
                  <Link href="/database" className="text-primary hover:underline">
                    Fetch leagues
                  </Link>
                </p>
              ) : (
                <ul className="space-y-1">
                  {recentDraftSyncs.map((s) => (
                    <li
                      key={s.league}
                      className="flex items-center justify-between text-xs"
                    >
                      <Badge variant="outline" className="text-[10px]">
                        {s.league}
                      </Badge>
                      <span className="text-muted-foreground">
                        {s.lastFetched
                          ? new Date(s.lastFetched).toLocaleString("en-US")
                          : "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">
                Players (per league)
              </div>
              {recentLeaguePlayerSyncs.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No syncs.{" "}
                  <Link
                    href="/players-data/league"
                    className="text-primary hover:underline"
                  >
                    Pick a league
                  </Link>
                </p>
              ) : (
                <ul className="space-y-1">
                  {recentLeaguePlayerSyncs.map((s) => (
                    <li
                      key={s.league}
                      className="flex items-center justify-between text-xs"
                    >
                      <Badge variant="outline" className="text-[10px]">
                        {s.league}
                      </Badge>
                      <span className="text-muted-foreground">
                        {s.count ?? 0} players ·{" "}
                        {s.lastFetched
                          ? new Date(s.lastFetched).toLocaleDateString("en-US")
                          : "—"}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="text-center pt-4">
        <Link
          href="/scouting"
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          → Go to player list
        </Link>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  href,
  extra,
}: {
  icon: React.ReactNode;
  label: string;
  value: number | string;
  href: string;
  extra?: React.ReactNode;
}) {
  return (
    <Link href={href} className="block">
      <Card className="hover:bg-muted/40 transition-colors h-full">
        <CardHeader className="pb-2">
          <div className="flex items-center gap-2 text-muted-foreground">
            {icon}
            <CardDescription>{label}</CardDescription>
          </div>
          <CardTitle className="text-3xl tabular-nums">{value}</CardTitle>
          {extra}
        </CardHeader>
      </Card>
    </Link>
  );
}
