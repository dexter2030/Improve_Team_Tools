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

/**
 * Surowy wiersz statystyk gracza z jednego meczu (ScoreboardPlayers + join do
 * ScoreboardGames po datę/długość/ligę). Bogatszy niż ScoreboardRow (które
 * służy champion-poolowi) — używany przez ranking kariery (src/lib/ranking/).
 * `link` = OverviewPage (stabilny join key). `league` = krótka nazwa z zapytania.
 */
export interface ScoreboardPlayerRow {
  readonly link: string;
  readonly role: string | null;
  readonly year: number;
  readonly league: string;
  readonly win: boolean;
  readonly gameLength: number | null; // minuty; null gdy brak / 0
  readonly kills: number;
  readonly deaths: number;
  readonly assists: number;
  readonly cs: number;
  readonly gold: number;
  readonly damage: number;
  readonly teamKills: number;
  readonly teamGold: number;
}

export type AuthStatus =
  | { level: "ok"; message: string }
  | { level: "info"; message: string }
  | { level: "warn"; message: string };
