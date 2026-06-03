import type { SeasonScore } from "@/lib/ranking/score";
import { SPLIT_FALLBACK } from "@/lib/leaguepedia/split";

/** Skrót etykiety splitu na chip: Spring→Spr, Summer→Sum, Winter→Win, Split 1→S1. */
function shortSplit(split: string): string {
  const m = split.match(/^Split\s*(\d)$/i);
  if (m) return `S${m[1]}`;
  const abbr: Record<string, string> = {
    Spring: "Spr",
    Summer: "Sum",
    Winter: "Win",
    Fall: "Fall",
  };
  return abbr[split] ?? split;
}

/**
 * Forma split-do-splitu: po jednym chipie na split (rok + split + Z-score w
 * kohorcie rola×liga×rok×split). Zielony = powyżej kohorty, czerwony = poniżej,
 * „·" = brak policzalnego Z. Tytuł chipa pokazuje ligę, split i liczbę gier.
 * Split „Sezon" (event bez splitów, np. MSI/Worlds) renderujemy bez etykiety.
 */
export function SplitTrend({ perSplit }: { perSplit: SeasonScore[] }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-xs">
      {perSplit.map((y) => (
        <span
          key={`${y.year}-${y.league}-${y.split}`}
          title={`${y.league} · ${y.split} (${y.games} gier)`}
          className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 tabular-nums"
        >
          <span className="text-muted-foreground">
            &apos;{String(y.year).slice(2)}
            {y.split !== SPLIT_FALLBACK && (
              <span className="ml-1">{shortSplit(y.split)}</span>
            )}
          </span>
          <span
            className={
              y.z === null
                ? "text-muted-foreground"
                : y.z >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
            }
          >
            {y.z === null ? "·" : (y.z >= 0 ? "+" : "") + y.z.toFixed(1)}
          </span>
        </span>
      ))}
    </div>
  );
}
