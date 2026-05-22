import { AddPlayerForm } from "./add-player-form";

const ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"] as const;

interface Props {
  searchParams: Promise<{
    displayName?: string;
    role?: string;
    nationality?: string;
    leaguepediaUrl?: string;
    lolprosUrl?: string;
  }>;
}

export default async function AddPlayerPage({ searchParams }: Props) {
  const sp = await searchParams;
  const role = sp.role && (ROLES as readonly string[]).includes(sp.role)
    ? (sp.role as (typeof ROLES)[number])
    : undefined;
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">
          Add player to watchlist
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Paste op.gg and Leaguepedia links — verified live against Riot API and Cargo API.
          Age, country and notes are your scouting metadata.
        </p>
      </div>
      <AddPlayerForm
        initialDisplayName={sp.displayName}
        initialRole={role}
        initialNationality={sp.nationality}
        initialLeaguepediaUrl={sp.leaguepediaUrl}
        initialLolprosUrl={sp.lolprosUrl}
      />
    </div>
  );
}
