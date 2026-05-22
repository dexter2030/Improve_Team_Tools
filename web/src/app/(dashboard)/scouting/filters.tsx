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
const ROLES = ["Top", "Jungle", "Mid", "Bot", "Support"] as const;
const STATUSES = ["resolved", "partial", "failed", "unresolved"] as const;

export function ScoutingFilters() {
  const router = useRouter();
  const sp = useSearchParams();

  function update(key: string, value: string | null) {
    const next = new URLSearchParams(sp.toString());
    if (!value || value === ALL) next.delete(key);
    else next.set(key, value);
    router.push(`/scouting?${next.toString()}`);
  }

  function onSearch(value: string) {
    window.clearTimeout((window as unknown as { __s?: number }).__s);
    (window as unknown as { __s?: number }).__s = window.setTimeout(
      () => update("search", value),
      300
    );
  }

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <Input
        placeholder="Search (name, team, Leaguepedia)..."
        defaultValue={sp.get("search") ?? ""}
        onChange={(e) => onSearch(e.target.value)}
      />
      <Select
        value={sp.get("role") ?? ALL}
        onValueChange={(v) => update("role", v)}
      >
        <SelectTrigger>
          <SelectValue placeholder="All roles" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All roles</SelectItem>
          {ROLES.map((r) => (
            <SelectItem key={r} value={r}>
              {r}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <Select
        value={sp.get("status") ?? ALL}
        onValueChange={(v) => update("status", v)}
      >
        <SelectTrigger>
          <SelectValue placeholder="All statuses" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All statuses</SelectItem>
          {STATUSES.map((s) => (
            <SelectItem key={s} value={s}>
              {s}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
