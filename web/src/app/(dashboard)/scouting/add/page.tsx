import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function AddPlayerPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Dodaj gracza do obserwacji</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Wklej linki op.gg i Leaguepedia — zostaną zweryfikowane na żywo przez Riot API i Cargo API.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Formularz dodawania</CardTitle>
          <CardDescription>Faza 6 — implementacja po podłączeniu Riot/Leaguepedia w TS</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder)</p>
        </CardContent>
      </Card>
    </div>
  );
}
