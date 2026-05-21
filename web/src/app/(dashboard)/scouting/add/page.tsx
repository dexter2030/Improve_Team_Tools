import { AddPlayerForm } from "./add-player-form";

export default function AddPlayerPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">
          Dodaj gracza do obserwacji
        </h2>
        <p className="text-sm text-muted-foreground mt-1">
          Wklej linki op.gg i Leaguepedia — zostaną zweryfikowane na żywo przez
          Riot API i Cargo API. Wiek, kraj i notatka to Twoje metadane
          scoutingowe.
        </p>
      </div>
      <AddPlayerForm />
    </div>
  );
}
