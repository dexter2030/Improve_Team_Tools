"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

type SortColumn = "id" | "role" | "team" | "country" | "isRetired";

export function SortHeader({
  column,
  label,
  align,
}: {
  column: SortColumn;
  label: string;
  align?: "left" | "right";
}) {
  const router = useRouter();
  const sp = useSearchParams();

  const sort = sp.get("sort") ?? "";
  const [activeCol, activeDir] = sort.split(":") as [string, string | undefined];
  const isActive = activeCol === column;
  const dir = isActive ? (activeDir === "desc" ? "desc" : "asc") : null;

  function toggle() {
    const next = new URLSearchParams(sp.toString());
    if (!isActive) {
      next.set("sort", `${column}:asc`);
    } else if (dir === "asc") {
      next.set("sort", `${column}:desc`);
    } else {
      next.delete("sort");
    }
    // Reset page do 1 przy zmianie sortowania.
    next.delete("page");
    router.push(`/players-data?${next.toString()}`);
  }

  const Icon = !isActive ? ArrowUpDown : dir === "asc" ? ArrowUp : ArrowDown;

  return (
    <button
      onClick={toggle}
      className={`inline-flex items-center gap-1 hover:text-foreground transition-colors ${
        isActive ? "text-foreground font-semibold" : ""
      } ${align === "right" ? "flex-row-reverse" : ""}`}
    >
      {label}
      <Icon className="h-3 w-3" />
    </button>
  );
}
