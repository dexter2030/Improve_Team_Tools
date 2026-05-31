/**
 * Niska warstwa Cargo API (MediaWiki) na lol.fandom.com.
 *
 * Cargo to extension MediaWiki — query przez ?action=cargoquery zwraca
 * { cargoquery: [{ title: {...} }, ...] }. Per-query limit 500; nad to
 * paginujemy przez `offset`. Tu zostawiamy single-query API + helper
 * paginacji — wystarcza na MVP (scoreboard per player mieści się w 500).
 *
 * Auth:
 * - Anon mode (default): per-IP rate limit ~1 req / 30s. Dla developmentu
 *   z jednego IP bardzo łatwo go uderzyć.
 * - Bot-password (LEAGUEPEDIA_USERNAME + LEAGUEPEDIA_PASSWORD w env):
 *   wyższy limit, lazy login na pierwszym requeście. Login flow:
 *     1) GET ?action=query&meta=tokens&type=login → loginToken
 *     2) POST action=login z lgname/lgpassword/lgtoken + cookies
 *     3) Następne requesty wysyłają zebrany cookie jar
 *   Singleton CargoSession trzyma cookies między requestami w procesie.
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

// --- Session (cookie jar + lazy login) -------------------------------------

class CargoSession {
  private cookies = new Map<string, string>();
  private loginPromise: Promise<void> | null = null;
  private authState: "anon" | "bot" | "error" = "anon";

  /** Zwraca cookie header lub null jeśli nic nie ma. */
  cookieHeader(): string | null {
    if (this.cookies.size === 0) return null;
    return [...this.cookies.entries()].map(([k, v]) => `${k}=${v}`).join("; ");
  }

  /** Wchłania set-cookie z response (Node 18+ ma getSetCookie()). */
  ingest(res: Response): void {
    const setCookies = res.headers.getSetCookie();
    for (const raw of setCookies) {
      const head = raw.split(";")[0];
      const eq = head.indexOf("=");
      if (eq > 0) {
        this.cookies.set(head.slice(0, eq).trim(), head.slice(eq + 1).trim());
      }
    }
  }

  /**
   * Lazy login. Idempotentne — wiele równoległych callerów dostaje ten
   * sam promise. Brak credentials → no-op (zostajemy w anon mode).
   */
  async ensureLoggedIn(fetcher: typeof fetch): Promise<void> {
    if (this.authState === "bot" || this.authState === "error") return;
    const username = process.env.LEAGUEPEDIA_USERNAME;
    const password = process.env.LEAGUEPEDIA_PASSWORD;
    if (!username || !password) return; // anon mode

    if (this.loginPromise) return this.loginPromise;
    this.loginPromise = this.doLogin(fetcher, username, password).catch(
      (err) => {
        this.authState = "error";
        console.warn("[leaguepedia] bot login failed:", err);
      }
    );
    return this.loginPromise;
  }

  private async doLogin(
    fetcher: typeof fetch,
    username: string,
    password: string
  ): Promise<void> {
    // Step 1: login token
    const tokenRes = await fetcher(
      `${CARGO_URL}?action=query&meta=tokens&type=login&format=json`,
      { headers: { "User-Agent": USER_AGENT }, cache: "no-store" }
    );
    this.ingest(tokenRes);
    const tokenJson = (await tokenRes.json()) as {
      query?: { tokens?: { logintoken?: string } };
    };
    const loginToken = tokenJson.query?.tokens?.logintoken;
    if (!loginToken) throw new Error("No login token from MediaWiki.");

    // Step 2: login POST
    const body = new URLSearchParams({
      action: "login",
      lgname: username,
      lgpassword: password,
      lgtoken: loginToken,
      format: "json",
    });
    const cookieHeader = this.cookieHeader();
    const loginRes = await fetcher(CARGO_URL, {
      method: "POST",
      headers: {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded",
        ...(cookieHeader ? { Cookie: cookieHeader } : {}),
      },
      body: body.toString(),
      cache: "no-store",
    });
    this.ingest(loginRes);
    const loginJson = (await loginRes.json()) as {
      login?: { result?: string; reason?: string };
    };
    if (loginJson.login?.result !== "Success") {
      throw new Error(
        `MediaWiki login failed: ${loginJson.login?.result ?? "unknown"}${
          loginJson.login?.reason ? " — " + loginJson.login.reason : ""
        }`
      );
    }
    this.authState = "bot";
  }

  getAuthState(): "anon" | "bot" | "error" {
    return this.authState;
  }
}

// Singleton w procesie — cookie jar persists między requestami.
let _session: CargoSession | null = null;

function getSession(): CargoSession {
  if (!_session) _session = new CargoSession();
  return _session;
}

export function getCargoAuthState(): "anon" | "bot" | "error" {
  return getSession().getAuthState();
}

// --- Cargo query -----------------------------------------------------------

/**
 * Single Cargo query z retry na transient errors (`ratelimited`,
 * HTTP 5xx). Backoff exp. 1→2→4→8s, max 4 próby.
 *
 * Bez retry na 4xx innych niż 429 — to błędy zapytania.
 */
export async function cargoQuery(
  q: CargoQuery,
  opts?: { fetcher?: typeof fetch; maxAttempts?: number }
): Promise<CargoRow[]> {
  const fetcher = opts?.fetcher ?? fetch;
  const maxAttempts = opts?.maxAttempts ?? 4;
  const session = getSession();
  await session.ensureLoggedIn(fetcher);

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
      const cookieHeader = session.cookieHeader();
      const res = await fetcher(url, {
        headers: {
          "User-Agent": USER_AGENT,
          ...(cookieHeader ? { Cookie: cookieHeader } : {}),
        },
        cache: "no-store",
      });
      session.ingest(res);

      if (res.status === 429 || res.status >= 500) {
        lastErr = new CargoError(
          `Leaguepedia Cargo HTTP ${res.status} (transient, retrying)`,
          res.status
        );
        continue;
      }
      if (!res.ok) {
        throw new CargoError(
          `Leaguepedia Cargo returned HTTP ${res.status}`,
          res.status
        );
      }

      const json = (await res.json()) as CargoResponse;
      if (json.error) {
        // 'ratelimited' (Cargo's own throttle, not HTTP 429) — retry.
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
 * Paginowany Cargo query — łączy strony po CARGO_LIMIT do wyczerpania
 * lub maxRows.
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

// --- Konwersje wartości ----------------------------------------------------

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
