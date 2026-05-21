import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function PlayersDataPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Players Data</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Pełna eksploracja statystyk zawodników z Leaguepedia ScoreboardPlayers.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Eksploruj graczy</CardTitle>
          <CardDescription>Faza 8 — port players_data_page.py na TS.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder)</p>
        </CardContent>
      </Card>
    </div>
  );
}
