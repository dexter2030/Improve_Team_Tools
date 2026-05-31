/**
 * GET /api/scouting/export
 *
 * Generuje CSV ze wszystkich profili — format symetryczny do bulk
 * importu (/scouting/import), więc plik się da skopiować w drugą
 * stronę bez ręcznego mapowania.
 *
 * Bonus kolumny ponad import: resolutionState, profileId, createdAt,
 * leaguepediaTeam (zresolwowane). Ignorowane podczas re-importu.
 */

import { listProfiles } from "@/lib/profiles/repository";

const COLUMNS = [
  "displayName",
  "role",
  "age",
  "nationality",
  "opggUrls",
  "leaguepediaUrl",
  "lolprosUrl",
  "notes",
  "resolutionState",
  "leaguepediaTeam",
  "profileId",
] as const;

export async function GET() {
  const profiles = await listProfiles();
  const lines = [COLUMNS.join(",")];

  for (const p of profiles) {
    const row = [
      p.displayName,
      p.role,
      p.age ?? "",
      p.nationality ?? "",
      // Multi op.gg separated by "|" — symetria z importem.
      p.soloq
        .map((s) => s.opggUrl)
        .filter(Boolean)
        .join("|"),
      p.proplay?.leaguepediaUrl ?? "",
      p.lolprosUrl ?? "",
      p.notes,
      p.resolutionState,
      p.proplay?.currentTeam ?? "",
      p.profileId,
    ];
    lines.push(row.map(escapeCsv).join(","));
  }

  const csv = lines.join("\n");
  const filename = `scouting-${new Date().toISOString().slice(0, 10)}.csv`;
  return new Response(csv, {
    status: 200,
    headers: {
      "Content-Type": "text/csv; charset=utf-8",
      "Content-Disposition": `attachment; filename="${filename}"`,
      "Cache-Control": "no-store",
    },
  });
}

/** Standardowy CSV escape: cudzysłowy podwajamy, pole z separatorem
 *  / newlinem / cudzysłowem wrappujemy w cudzysłowy. */
function escapeCsv(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  if (s === "") return "";
  if (s.includes(",") || s.includes("\n") || s.includes('"')) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}
