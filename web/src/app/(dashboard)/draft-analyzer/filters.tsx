"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { LEAGUE_GROUPS } from "@/lib/leaguepedia/leagues";

export function Filters({ patches }: { patches: string[] }) {
  const router = useRouter();
  const sp = useSearchParams();
  const activeLeagues = (sp.get("league") ?? "").split(",").filter(Boolean);
  const activePatches = (sp.get("patch") ?? "").split(",").filter(Boolean);

  function update(key: string, values: string[]) {
    const next = new URLSearchParams(sp.toString());
    if (values.length === 0) next.delete(key);
    else next.set(key, values.join(","));
    router.push(`/draft-analyzer?${next.toString()}`);
  }

  function toggle(key: "league" | "patch", value: string) {
    const current = key === "league" ? activeLeagues : activePatches;
    const next = current.includes(value)
      ? current.filter((v) => v !== value)
      : [...current, value];
    update(key, next);
  }

  function clear() {
    router.push("/draft-analyzer");
  }

  function preset(leagues: readonly string[]) {
    update("league", [...leagues]);
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm font-medium">
          Presety lig:
          <Button size="xs" variant="outline" onClick={() => preset(LEAGUE_GROUPS.tier1)}>
            Tier 1
          </Button>
          <Button size="xs" variant="outline" onClick={() => preset([...LEAGUE_GROUPS.tier1, ...LEAGUE_GROUPS.erlD1])}>
            + ERL D1
          </Button>
          <Button size="xs" variant="outline" onClick={clear}>
            Wyczyść
          </Button>
        </div>

        <div className="flex flex-wrap gap-1.5">
          {[...LEAGUE_GROUPS.tier1, ...LEAGUE_GROUPS.erlD1, ...LEAGUE_GROUPS.erlD2].map(
            (l) => (
              <button
                key={l}
                onClick={() => toggle("league", l)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  activeLeagues.includes(l)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border hover:bg-muted"
                }`}
              >
                {l}
              </button>
            )
          )}
        </div>
      </div>

      {patches.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm font-medium flex-wrap">
            Presety patchy:
            <Button
              size="xs"
              variant="outline"
              onClick={() => update("patch", patches.slice(0, 5))}
            >
              Ostatnie 5
            </Button>
            <Button
              size="xs"
              variant="outline"
              onClick={() => update("patch", patches.slice(0, 10))}
            >
              Ostatnie 10
            </Button>
            <Button
              size="xs"
              variant="outline"
              onClick={() => update("patch", [])}
            >
              Wszystkie patche
            </Button>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {patches.map((p) => (
              <button
                key={p}
                onClick={() => toggle("patch", p)}
                className={`text-xs px-2 py-1 rounded border transition-colors ${
                  activePatches.includes(p)
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border hover:bg-muted"
                }`}
              >
                {p}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
