import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default function ScoutingListPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Tracked players</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Lista obserwowanych zawodników z rozwiązanymi tożsamościami SoloQ i pro-play.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Total" value="—" />
        <StatCard label="Resolved" value="—" />
        <StatCard label="Partial" value="—" />
        <StatCard label="Failed / Unresolved" value="—" />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Pusto</CardTitle>
          <CardDescription>
            Nie ma jeszcze żadnych zawodników. Dodaj pierwszego w zakładce{" "}
            <Badge variant="secondary">Add Player</Badge>.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            (placeholder — Faza 6 podłączy live dane z Supabase)
          </p>
        </CardContent>
      </Card>
    </div>
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-3xl">{value}</CardTitle>
      </CardHeader>
    </Card>
  );
}
