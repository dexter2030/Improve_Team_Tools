"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { ArrowDown, ArrowUp, ArrowUpDown } from "lucide-react";

export type RankSortColumn =
  | "player"
  | "league"
  | "role"
  | "age"
  | "games"
  | "rating"
  | "potential";

const DEFAULT_SORT = "rating:desc";

export function RankingSortHeader({
  column,
  label,
  align,
}: {
  column: RankSortColumn;
  label: string;
  align?: "left" | "right";
}) {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();

  const sort = sp.get("sort") ?? DEFAULT_SORT;
  const [activeCol, activeDir] = sort.split(":") as [string, string | undefined];
  const isActive = activeCol === column;
  const dir = isActive ? (activeDir === "asc" ? "asc" : "desc") : null;

  function toggle() {
    const next = new URLSearchParams(sp.toString());
    // Pierwsze kliknięcie → malejąco (najprzydatniejsze dla ocena/potencjał),
    // drugie → rosnąco, trzecie → powrót do domyślnego (ocena malejąco).
    if (!isActive) next.set("sort", `${column}:desc`);
    else if (dir === "desc") next.set("sort", `${column}:asc`);
    else next.delete("sort");
    router.push(`${pathname}?${next.toString()}`);
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
