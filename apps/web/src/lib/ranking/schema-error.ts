/**
 * Rozpoznanie błędu „schemat bazy starszy niż kod" — tabele/kolumny rankingu
 * (migracje 0007/0008) nieprzeparte na bazie tego deploymentu. Pozwala stronom
 * rankingu zdegradować się do czytelnej notki zamiast crashować całą trasę
 * (Server Component → error.tsx → zamaskowany błąd produkcyjny).
 *
 * Kody SQLSTATE z postgres-js: 42P01 = undefined_table, 42703 = undefined_column.
 */

const SCHEMA_BEHIND_CODES = new Set(["42P01", "42703"]);

export function isSchemaBehindError(err: unknown): boolean {
  const code = (err as { code?: unknown })?.code;
  return typeof code === "string" && SCHEMA_BEHIND_CODES.has(code);
}
