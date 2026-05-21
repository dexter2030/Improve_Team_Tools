"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

export function Pagination({
  page,
  totalPages,
  total,
  pageSize,
}: {
  page: number;
  totalPages: number;
  total: number;
  pageSize: number;
}) {
  const router = useRouter();
  const sp = useSearchParams();

  function goTo(n: number) {
    const next = new URLSearchParams(sp.toString());
    if (n <= 1) next.delete("page");
    else next.set("page", String(n));
    router.push(`/players-data?${next.toString()}`);
  }

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);

  return (
    <div className="flex items-center justify-between gap-4 px-4 py-3 border-t">
      <div className="text-xs text-muted-foreground">
        {total === 0
          ? "Brak wyników"
          : `${from.toLocaleString("pl-PL")}-${to.toLocaleString("pl-PL")} z ${total.toLocaleString("pl-PL")}`}
      </div>
      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => goTo(page - 1)}
          disabled={page <= 1}
        >
          <ChevronLeft className="h-3.5 w-3.5 mr-1" />
          Poprzednia
        </Button>
        <span className="text-xs text-muted-foreground tabular-nums">
          {page} / {totalPages}
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => goTo(page + 1)}
          disabled={page >= totalPages}
        >
          Następna
          <ChevronRight className="h-3.5 w-3.5 ml-1" />
        </Button>
      </div>
    </div>
  );
}
