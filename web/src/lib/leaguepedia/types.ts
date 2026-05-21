/**
 * Typy Leaguepedia (Cargo) — odpowiedniki dataclasses z
 * src/api/leaguepedia_client.py.
 *
 * `link` w PlayerIdentityRow / ScoreboardRow to OverviewPage —
 * canonical wiki page name, stabilny join key. Nie joinuj po `playerId`
 * (in-game handle, zmienny).
 */

export interface PlayerIdentityRow {
  readonly link: string;
  readonly playerId: string;
  readonly team: string;
  readonly role: string;
}

export interface PlayerMetaRow {
  readonly overviewPage: string;
  readonly id: string;
  readonly team: string;
  readonly role: string;
  readonly country: string;
  readonly residency: string;
  readonly nationalityPrimary: string;
  readonly isRetired: boolean;
}

export interface ScoreboardRow {
  readonly gameId: string;
  readonly champion: string;
  readonly kills: number;
  readonly deaths: number;
  readonly assists: number;
  readonly cs: number;
  readonly win: boolean;
}

export type AuthStatus =
  | { level: "ok"; message: string }
  | { level: "info"; message: string }
  | { level: "warn"; message: string };
