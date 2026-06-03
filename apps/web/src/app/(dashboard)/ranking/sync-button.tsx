"use client";

import { useTransition } from "react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { Download, RefreshCw } from "lucide-react";
import { syncLeagueStatsAction } from "./actions";

export function RankingSyncButton({
  league,
  hasData,
}: {
  league: string;
  hasData: boolean;
}) {
  const [pending, startTransition] = useTransition();

  function sync() {
    startTransition(async () => {
      const r = await syncLeagueStatsAction(league);
      if (r.error) toast.error(`${league}: ${r.error}`);
      else
        toast.success(
          `${league}: ${r.saved} sezonów graczy (z ${r.fetched} gier)`
        );
    });
  }

  return (
    <Button
      onClick={sync}
      disabled={pending}
      size="sm"
      variant={hasData ? "outline" : "default"}
    >
      {pending ? (
        "..."
      ) : hasData ? (
        <>
          <RefreshCw className="h-3.5 w-3.5 mr-1" /> Odśwież
        </>
      ) : (
        <>
          <Download className="h-3.5 w-3.5 mr-1" /> Pobierz
        </>
      )}
    </Button>
  );
}
