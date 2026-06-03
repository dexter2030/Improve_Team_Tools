import type { SeasonScore } from "@/lib/ranking/score";

/**
 * Forma rok-do-roku: po jednym chipie na sezon (rok + Z-score w kohorcie).
 * Zielony = powyżej kohorty, czerwony = poniżej, „·" = brak policzalnego Z.
 * Tytuł chipa pokazuje ligę i liczbę gier danego sezonu.
 */
export function YearTrend({ perYear }: { perYear: SeasonScore[] }) {
  return (
    <div className="flex flex-wrap gap-1.5 text-xs">
      {perYear.map((y) => (
        <span
          key={`${y.year}-${y.league}`}
          title={`${y.league} (${y.games} gier)`}
          className="inline-flex items-center gap-1 rounded bg-muted px-1.5 py-0.5 tabular-nums"
        >
          <span className="text-muted-foreground">
            &apos;{String(y.year).slice(2)}
          </span>
          <span
            className={
              y.yearZ === null
                ? "text-muted-foreground"
                : y.yearZ >= 0
                  ? "text-emerald-600 dark:text-emerald-400"
                  : "text-red-600 dark:text-red-400"
            }
          >
            {y.yearZ === null
              ? "·"
              : (y.yearZ >= 0 ? "+" : "") + y.yearZ.toFixed(1)}
          </span>
        </span>
      ))}
    </div>
  );
}
