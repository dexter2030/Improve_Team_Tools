/**
 * Lista lig + presety. Port draft_analyzer/leagues.py.
 *
 * moreSpecific() wymusza na każdej warstwie wykluczanie bardziej
 * szczegółowych nazw — Tournament w Leaguepedia LIKE '%LFL%' łapie też
 * "LFL Division 2", co fałszuje dane Tier 1 vs Tier 2.
 */

export const LEAGUE_GROUPS = {
  tier1: ["LEC", "LCK", "LPL", "LCS", "MSI", "Worlds", "First Stand"],
  erlD1: [
    "LFL",
    "PRM 1st Division",
    "LVP SL",
    "NLC",
    "Hitpoint Masters",
    "Esports Balkan League",
    "Liga Portuguesa",
    "Greek Legends League",
    "Ultraliga",
    "TCL",
    "PG Nationals",
    "Arabian League",
    "LPLOL",
  ],
  erlD2: [
    "LFL Division 2",
    "PRM 2nd Division",
    "NLC Division 2",
    "Hitpoint Masters Division 2",
    "Liga Portuguesa Division 2",
    "Greek Legends League Division 2",
    "TCL Academy League",
  ],
} as const;

export const ALL_LEAGUES: readonly string[] = [
  ...LEAGUE_GROUPS.tier1,
  ...LEAGUE_GROUPS.erlD1,
  ...LEAGUE_GROUPS.erlD2,
];

const _MORE_SPECIFIC: Record<string, string[]> = {
  LFL: ["LFL Division 2"],
  PRM: ["PRM 1st Division", "PRM 2nd Division"],
  "PRM 1st Division": ["PRM 2nd Division"],
  NLC: ["NLC Division 2"],
  "Hitpoint Masters": ["Hitpoint Masters Division 2"],
  "Liga Portuguesa": ["Liga Portuguesa Division 2"],
  "Greek Legends League": ["Greek Legends League Division 2"],
  TCL: ["TCL Academy League"],
  LPL: ["LPLOL"],
};

/**
 * Zwraca bardziej szczegółowe nazwy lig, które trzeba wykluczyć przy
 * filtrowaniu/wyszukiwaniu po danym haśle.
 */
export function moreSpecific(league: string): string[] {
  return _MORE_SPECIFIC[league] ?? [];
}
