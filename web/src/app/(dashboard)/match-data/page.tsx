import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function MatchDataPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Match Data</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Szczegółowe statystyki per mecz — gold/min, damage share, vision per minute itd.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Eksploruj mecze</CardTitle>
          <CardDescription>Faza 8 — port match_data_page.py na TS.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder)</p>
        </CardContent>
      </Card>
    </div>
  );
}
