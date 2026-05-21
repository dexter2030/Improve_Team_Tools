"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import { syncPlayersAction } from "./actions";

export function SyncBar({
  count,
  lastFetched,
}: {
  count: number;
  lastFetched: Date | null;
}) {
  const [pending, startTransition] = useTransition();

  function sync() {
    startTransition(async () => {
      const result = await syncPlayersAction();
      if (result.error) {
        toast.error(`Błąd: ${result.error}`);
      } else {
        toast.success(
          `Pobrano ${result.fetched}, zapisano ${result.saved} graczy.`
        );
      }
    });
  }

  return (
    <div className="flex items-center justify-between gap-4 p-4 rounded-lg border bg-muted/30">
      <div className="text-sm">
        <div className="font-medium">Globalna baza graczy Leaguepedia</div>
        <div className="text-muted-foreground text-xs mt-0.5">
          {count > 0
            ? `${count.toLocaleString("pl-PL")} graczy w bazie · ostatnie pobranie: ${
                lastFetched
                  ? new Date(lastFetched).toLocaleString("pl-PL")
                  : "—"
              }`
            : "Brak danych — pobranie zajmuje ~1-2 minuty (~30k graczy)."}
        </div>
      </div>
      <Button onClick={sync} disabled={pending} variant={count > 0 ? "outline" : "default"}>
        {pending ? (
          "Pobieram..."
        ) : count > 0 ? (
          <>
            <RefreshCw className="h-4 w-4 mr-2" />
            Odśwież
          </>
        ) : (
          <>
            <Download className="h-4 w-4 mr-2" />
            Pobierz
          </>
        )}
      </Button>
    </div>
  );
}
