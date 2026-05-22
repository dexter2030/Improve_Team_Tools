import { AddPlayerForm } from "./add-player-form";

export default function AddPlayerPage() {
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
      <AddPlayerForm />
    </div>
  );
}
