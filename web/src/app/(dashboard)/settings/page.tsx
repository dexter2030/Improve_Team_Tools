import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Info } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Ustawienia</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Konfiguracja kluczy API i opcji aplikacji.
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Sekrety</AlertTitle>
        <AlertDescription>
          Na produkcji (Vercel) klucze ustawiasz w panelu Vercel → Environment Variables.
          Lokalnie w pliku <code className="font-mono text-xs">web/.env.local</code>.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Riot API key</CardTitle>
          <CardDescription>
            Klucz developerski wygasa co 24h — production key wymaga zatwierdzenia wniosku.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder — Faza 9 doda UI)</p>
        </CardContent>
      </Card>
    </div>
  );
}
