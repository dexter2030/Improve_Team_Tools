import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Info } from "lucide-react";

export default function SettingsPage() {
  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Settings</h2>
        <p className="text-sm text-muted-foreground mt-1">
          API keys and app options.
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertTitle>Secrets</AlertTitle>
        <AlertDescription>
          On prod (Vercel) set keys in Vercel → Environment Variables.
          Locally in <code className="font-mono text-xs">web/.env.local</code>.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Riot API key</CardTitle>
          <CardDescription>
            Dev key expires every 24h — production key requires approval.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder — UI coming later)</p>
        </CardContent>
      </Card>
    </div>
  );
}
