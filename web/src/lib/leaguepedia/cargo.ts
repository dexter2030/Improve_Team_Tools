/**
 * Niska warstwa Cargo API (MediaWiki) na lol.fandom.com.
 *
 * Cargo to extension MediaWiki — query przez ?action=cargoquery zwraca
 * { cargoquery: [{ title: {...} }, ...] }. Per-query limit 500; nad to
 * paginujemy przez `offset`. Tutaj zostawiamy single-query API +
 * helper na cienką paginację — wystarcza na MVP (scoreboard per player
 * mieści się w 500 wierszach).
 *
 * Tryb anonimowy. Bot-password (LEAGUEPEDIA_USERNAME/PASSWORD) podnosi
 * limit i jest TODO na później — w MVP klient anonimowy wystarcza dla
 * scoutingu pojedynczego gracza.
 */

const CARGO_URL = "https://lol.fandom.com/api.php";
const USER_AGENT =
  "improve-team-tools/0.1 (Leaguepedia client; identity + scouting)";
export const CARGO_LIMIT = 500;

export interface CargoQuery {
  tables: string;
  fields: string;
  where?: string;
  joinOn?: string;
  orderBy?: string;
  groupBy?: string;
  limit?: number;
  offset?: number;
}

export type CargoRow = Record<string, string | number | null>;

interface CargoResponse {
  cargoquery?: Array<{ title: CargoRow }>;
  error?: { code: string; info: string };
}

/**
 * Escape pojedynczego cudzysłowu w wartościach where dla SQL-like API.
 * MediaWiki nie ma ścisłej parametryzacji — escape jest po naszej stronie.
 */
export function cargoEscape(value: string): string {
  return value.replace(/'/g, "\\'");
}

/**
 * Single Cargo query z retry na transient errors (`ratelimited`,
 * HTTP 5xx). Backoff exponential 1s → 2s → 4s → 8s, max 4 próby.
 *
 * Bez retry na 4xx innych niż 429 — to błędy zapytania, retry nie pomoże.
 */
export async function cargoQuery(
  q: CargoQuery,
  opts?: { fetcher?: typeof fetch; maxAttempts?: number }
): Promise<CargoRow[]> {
  const fetcher = opts?.fetcher ?? fetch;
  const maxAttempts = opts?.maxAttempts ?? 4;
  const params = new URLSearchParams({
    action: "cargoquery",
    format: "json",
    tables: q.tables,
    fields: q.fields,
    limit: String(q.limit ?? CARGO_LIMIT),
  });
  if (q.where) params.set("where", q.where);
  if (q.joinOn) params.set("join_on", q.joinOn);
  if (q.orderBy) params.set("order_by", q.orderBy);
  if (q.groupBy) params.set("group_by", q.groupBy);
  if (q.offset) params.set("offset", String(q.offset));

  const url = `${CARGO_URL}?${params.toString()}`;

  let lastErr: unknown;
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (attempt > 0) {
      const backoff = Math.min(8000, 1000 * 2 ** (attempt - 1));
      await new Promise((r) => setTimeout(r, backoff));
    }
    try {
      const res = await fetcher(url, {
        headers: { "User-Agent": USER_AGENT },
        cache: "no-store",
      });

      if (res.status === 429 || res.status >= 500) {
        lastErr = new CargoError(
          `Leaguepedia Cargo HTTP ${res.status} (transient, retrying)`,
          res.status
        );
        continue;
      }
      if (!res.ok) {
        throw new CargoError(
          `Leaguepedia Cargo zwróciło HTTP ${res.status}`,
          res.status
        );
      }

      const json = (await res.json()) as CargoResponse;
      if (json.error) {
        // `ratelimited` (Cargo's own throttle, not HTTP 429) — retry.
        if (json.error.code === "ratelimited") {
          lastErr = new CargoError(
            `Cargo ratelimited (retrying): ${json.error.info}`,
            429
          );
          continue;
        }
        throw new CargoError(
          `Cargo error: ${json.error.code} — ${json.error.info}`,
          400
        );
      }
      return (json.cargoquery ?? []).map((r) => r.title);
    } catch (err) {
      // Sieciowe — retry. Bizn. (CargoError z 4xx innym niż 429) — propaguj.
      if (err instanceof CargoError && err.status < 500 && err.status !== 429) {
        throw err;
      }
      lastErr = err;
    }
  }
  throw lastErr instanceof Error
    ? lastErr
    : new CargoError("Cargo query failed after retries", 500);
}

/**
 * Paginowany Cargo query — łączy strony po `CARGO_LIMIT` aż do wyczerpania
 * lub osiągnięcia maxRows.
 */
export async function cargoPaginated(
  q: CargoQuery,
  maxRows = 20000,
  opts?: { fetcher?: typeof fetch }
): Promise<CargoRow[]> {
  const out: CargoRow[] = [];
  let offset = q.offset ?? 0;
  while (out.length < maxRows) {
    const rows = await cargoQuery({ ...q, offset, limit: CARGO_LIMIT }, opts);
    if (rows.length === 0) break;
    out.push(...rows);
    if (rows.length < CARGO_LIMIT) break;
    offset += CARGO_LIMIT;
  }
  return out.slice(0, maxRows);
}

export class CargoError extends Error {
  constructor(message: string, public readonly status: number) {
    super(message);
    this.name = "CargoError";
  }
}

// --- Pomocniki konwersji wartości -----------------------------------------

export function toInt(value: unknown): number {
  if (typeof value === "number") return Math.trunc(value);
  if (typeof value === "string" && value.trim() !== "") {
    const n = Number(value);
    return Number.isFinite(n) ? Math.trunc(n) : 0;
  }
  return 0;
}

export function toBool(value: unknown): boolean {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    return v === "yes" || v === "true" || v === "1";
  }
  return false;
}

export function toStr(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}
