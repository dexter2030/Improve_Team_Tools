import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function DatabasePage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Database</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Eksplorator zapisanych draftów i synchronizacja z Leaguepedia.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Status synchronizacji</CardTitle>
          <CardDescription>Faza 8 — UI dla zarządzania bazą draftów.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder)</p>
        </CardContent>
      </Card>
    </div>
  );
}
