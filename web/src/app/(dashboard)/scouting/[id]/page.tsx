import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { buttonVariants } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/status-badge";
import { getProfile } from "@/lib/profiles/repository";
import { ProfileActions } from "./profile-actions";
import { NotesEditor } from "./notes-editor";
import { RankedPanel } from "./ranked-panel";
import { ChampionPoolPanel } from "./champion-pool-panel";
import { ArrowLeft } from "lucide-react";

export const dynamic = "force-dynamic";

interface Props {
  params: Promise<{ id: string }>;
}

export default async function ProfileDetailPage({ params }: Props) {
  const { id } = await params;
  const profile = await getProfile(id);
  if (!profile) notFound();

  const nResolved = profile.soloq.filter((s) => s.puuid !== null).length;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between">
        <div>
          <Link
            href="/scouting"
            className={`${buttonVariants({ variant: "ghost", size: "sm" })} mb-2 -ml-2`}
          >
            <ArrowLeft className="h-4 w-4 mr-1" /> All players
          </Link>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-semibold tracking-tight">
              {profile.displayName}
            </h2>
            <StatusBadge state={profile.resolutionState} />
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            {profile.role} · age {profile.age ?? "—"} · {profile.nationality ?? "—"}
          </p>
        </div>
        <ProfileActions id={profile.profileId} />
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Role" value={profile.role} />
        <StatCard
          label="op.gg accounts"
          value={profile.soloq.length ? `${nResolved}/${profile.soloq.length}` : "—"}
        />
        <StatCard
          label="Team (pro)"
          value={profile.proplay?.currentTeam ?? "—"}
        />
        <StatCard
          label="Leaguepedia"
          value={profile.proplay?.verified ? "verified" : "—"}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Ranked stats</CardTitle>
          <CardDescription>
            Live from Riot League-V4. Cache: 1h (LP/tier shifts during play).
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<Skeleton className="h-24 w-full" />}>
            <RankedPanel accounts={profile.soloq} />
          </Suspense>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Champion pool (pro play)</CardTitle>
          <CardDescription>
            Per-champion aggregation from Leaguepedia ScoreboardPlayers. Cache 6h.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Suspense fallback={<Skeleton className="h-48 w-full" />}>
            <ChampionPoolPanel proplay={profile.proplay} />
          </Suspense>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>SoloQ accounts (op.gg)</CardTitle>
          <CardDescription>
            Accounts parsed from op.gg links, verified via Riot API.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {profile.soloq.length === 0 ? (
            <p className="text-sm text-muted-foreground">No SoloQ accounts on this profile.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {profile.soloq.map((s, i) => (
                <li key={i} className="flex items-center gap-3">
                  <code className="bg-muted px-2 py-0.5 rounded text-xs">
                    {s.riotId}
                  </code>
                  <span className="text-muted-foreground">({s.platform})</span>
                  <span>
                    {s.summonerLevel !== null
                      ? `level ${s.summonerLevel}`
                      : "unresolved"}
                  </span>
                  {s.opggUrl && (
                    <a
                      href={s.opggUrl}
                      target="_blank"
                      rel="noreferrer"
                      className="text-primary hover:underline ml-auto text-xs"
                    >
                      op.gg ↗
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {profile.proplay && (
        <Card>
          <CardHeader>
            <CardTitle>Pro play (Leaguepedia)</CardTitle>
            <CardDescription>
              Pro-play identity joined on the canonical wiki page name.
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm space-y-1">
            <div>
              <span className="text-muted-foreground">Link:</span>{" "}
              <code className="bg-muted px-2 py-0.5 rounded text-xs">
                {profile.proplay.leaguepediaLink}
              </code>
            </div>
            {profile.proplay.currentTeam && (
              <div>
                <span className="text-muted-foreground">Team:</span>{" "}
                {profile.proplay.currentTeam}
              </div>
            )}
            {profile.proplay.leaguepediaUrl && (
              <div>
                <a
                  href={profile.proplay.leaguepediaUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline text-xs"
                >
                  Leaguepedia ↗
                </a>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Separator />

      <Card>
        <CardHeader>
          <CardTitle>Scouting notes</CardTitle>
          <CardDescription>
            Your observations on this player.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <NotesEditor id={profile.profileId} initial={profile.notes} />
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
