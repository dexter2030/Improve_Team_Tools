import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function DraftAnalyzerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">Draft Analyzer</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Historyczna analiza pick &amp; ban — top compsy, win-rate per draft, response patterns.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Wczytaj drafty</CardTitle>
          <CardDescription>Faza 7 — port logiki z draft_analyzer/ na TypeScript.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">(placeholder)</p>
        </CardContent>
      </Card>
    </div>
  );
}
