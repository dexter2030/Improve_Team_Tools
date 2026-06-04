import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle } from "lucide-react";

/**
 * Notka degradacyjna: baza tego środowiska nie ma jeszcze schematu rankingu
 * (migracje 0007/0008 nieprzeparte). Pokazywana zamiast crasha trasy, gdy
 * `isSchemaBehindError` złapie 42P01/42703. Por. lib/ranking/schema-error.
 */
export function RankingSchemaNotice() {
  return (
    <Card>
      <CardContent className="py-10 text-center space-y-3">
        <AlertTriangle className="h-6 w-6 mx-auto text-destructive" />
        <div className="space-y-1">
          <p className="font-medium">Schemat rankingu nieaktualny na tej bazie</p>
          <p className="text-sm text-muted-foreground max-w-md mx-auto">
            Tabele rankingu nie są jeszcze zmigrowane na bazie tego środowiska.
            Z katalogu <code>apps/web</code> uruchom migracje i wczytaj dane:
          </p>
        </div>
        <pre className="text-xs bg-muted rounded-md p-3 inline-block text-left">
          npx drizzle-kit migrate{"\n"}npx tsx scripts/load-ranking.ts --force
        </pre>
      </CardContent>
    </Card>
  );
}
