"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const ALL = "__all__";
const PLAYERS_ONLY = "__players__";

export function PlayersFilters({
  roles,
  countries,
}: {
  roles: string[];
  countries: string[];
}) {
  const router = useRouter();
  const sp = useSearchParams();
  // Select shows either a concrete role, the players-only sentinel, or ALL.
  // URL stores either `role=<concrete>` or `playerRolesOnly=1` — never both.
  const playersOnly = sp.get("playerRolesOnly") === "1";
  const role = playersOnly ? PLAYERS_ONLY : (sp.get("role") ?? ALL);
  const country = sp.get("country") ?? ALL;
  const search = sp.get("search") ?? "";
  const hideRetired = sp.get("hideRetired") === "1";

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(sp.toString());
    if (!value || value === ALL) next.delete(key);
    else next.set(key, value);
    router.push(`/players-data?${next.toString()}`);
  }

  function updateRole(value: string) {
    const next = new URLSearchParams(sp.toString());
    if (value === PLAYERS_ONLY) {
      next.delete("role");
      next.set("playerRolesOnly", "1");
    } else {
      next.delete("playerRolesOnly");
      if (value === ALL) next.delete("role");
      else next.set("role", value);
    }
    router.push(`/players-data?${next.toString()}`);
  }

  return (
    <div className="grid gap-3 md:grid-cols-4">
      <Input
        placeholder="Search (name, team, wiki)..."
        defaultValue={search}
        onChange={(e) => {
          const v = e.target.value;
          // Debounce by deferring with setTimeout (cancel by tracking ref).
          window.clearTimeout((window as unknown as { __t?: number }).__t);
          (window as unknown as { __t?: number }).__t = window.setTimeout(
            () => update("search", v),
            300
          );
        }}
      />

      <Select value={role} onValueChange={updateRole}>
        <SelectTrigger>
          <SelectValue placeholder="All roles">
            {(v) =>
              v === ALL
                ? "All roles"
                : v === PLAYERS_ONLY
                  ? "Players only"
                  : v
            }
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All roles</SelectItem>
          <SelectItem value={PLAYERS_ONLY}>Players only (Top/Jungle/Mid/Bot/Support)</SelectItem>
          {roles.map((r) => (
            <SelectItem key={r} value={r}>
              {r}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={country} onValueChange={(v) => update("country", v)}>
        <SelectTrigger>
          <SelectValue placeholder="All countries">
            {(v) => (v === ALL ? "All countries" : v)}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All countries</SelectItem>
          {countries.map((c) => (
            <SelectItem key={c} value={c}>
              {c}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <label className="flex items-center gap-2 text-sm px-3 py-2 border rounded-md cursor-pointer hover:bg-muted/40">
        <input
          type="checkbox"
          checked={hideRetired}
          onChange={(e) =>
            update("hideRetired", e.target.checked ? "1" : null)
          }
        />
        Hide retired
      </label>
    </div>
  );
}
