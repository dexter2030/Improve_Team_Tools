import { cn } from "@/lib/utils";
import type { ResolutionState } from "@/lib/db/schema";

const STYLES: Record<ResolutionState, { bg: string; fg: string; label: string }> = {
  resolved: { bg: "bg-emerald-100", fg: "text-emerald-800", label: "RESOLVED" },
  partial: { bg: "bg-amber-100", fg: "text-amber-800", label: "PARTIAL" },
  failed: { bg: "bg-rose-100", fg: "text-rose-800", label: "FAILED" },
  unresolved: { bg: "bg-zinc-200", fg: "text-zinc-700", label: "UNRESOLVED" },
};

export function StatusBadge({ state }: { state: ResolutionState }) {
  const s = STYLES[state];
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-full text-[0.7rem] font-semibold tracking-wider",
        s.bg,
        s.fg
      )}
    >
      {s.label}
    </span>
  );
}
