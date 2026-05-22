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

export function PlayersFilters({
  roles,
  countries,
}: {
  roles: string[];
  countries: string[];
}) {
  const router = useRouter();
  const sp = useSearchParams();
  const role = sp.get("role") ?? ALL;
  const country = sp.get("country") ?? ALL;
  const search = sp.get("search") ?? "";
  const hideRetired = sp.get("hideRetired") === "1";

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(sp.toString());
    if (!value || value === ALL) next.delete(key);
    else next.set(key, value);
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

      <Select value={role} onValueChange={(v) => update("role", v)}>
        <SelectTrigger>
          <SelectValue placeholder="All roles" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All roles</SelectItem>
          {roles.map((r) => (
            <SelectItem key={r} value={r}>
              {r}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Select value={country} onValueChange={(v) => update("country", v)}>
        <SelectTrigger>
          <SelectValue placeholder="All countries" />
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
