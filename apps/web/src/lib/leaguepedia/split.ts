/**
 * Wyprowadzenie SPLITU z metadanych turnieju Leaguepedia (Tournaments.Split /
 * SplitNumber + nazwa strony/turnieju). To FETCH-side ekstrakcja pola ze źródła
 * (jak rok z DateTime_UTC) — NIE normalizacja scoringowa. Scoring (src/lib/ranking)
 * konsumuje gotowe `split` + `splitOrder`, nie zna parsowania nazw LP.
 *
 * Po przebudowie formatu w 2025 LP ma niejednorodne splity (Winter/Spring/Summer,
 * dawniej Spring/Summer, gdzieniegdzie "Split 1..3"). Gdy Tournaments.Split puste —
 * parsujemy nazwę strony/turnieju; gdy nic nie pasuje (MSI, Worlds, eventy bez
 * splitów) — pojedynczy bucket SPLIT_FALLBACK (degeneracja do grana rocznego).
 */

/** Bucket dla turniejów bez rozpoznanego splitu (np. MSI/Worlds) — jeden „sezon”. */
export const SPLIT_FALLBACK = "Sezon";

/**
 * Znane splity sezonowe + ich pozycja w roku (ułamek [0,1)) — do sortowania
 * chipów i osi x trajektorii. Kolejność = chronologia w sezonie.
 */
const KNOWN_SPLITS: ReadonlyArray<{ re: RegExp; label: string; frac: number }> = [
  { re: /\bwinter\b/i, label: "Winter", frac: 0.0 },
  { re: /\bspring\b/i, label: "Spring", frac: 0.25 },
  { re: /\bsummer\b/i, label: "Summer", frac: 0.5 },
  { re: /\b(?:fall|autumn)\b/i, label: "Fall", frac: 0.75 },
];

/** Kanoniczna etykieta splitu z dowolnego stringa; "" gdy nie rozpoznano. */
function canonicalSplit(text: string): string {
  for (const k of KNOWN_SPLITS) if (k.re.test(text)) return k.label;
  const m = text.match(/\bsplit\s*([1-4])\b/i);
  if (m) return `Split ${m[1]}`;
  return "";
}

/**
 * Etykieta splitu: priorytet Tournaments.Split, potem nazwa strony, potem nazwa
 * turnieju; ostatecznie SPLIT_FALLBACK.
 */
export function deriveSplit(
  rawSplit: string,
  tournamentPage: string,
  tournamentName: string
): string {
  return (
    canonicalSplit(rawSplit) ||
    canonicalSplit(tournamentPage) ||
    canonicalSplit(tournamentName) ||
    SPLIT_FALLBACK
  );
}

/**
 * Ułamek roku [0,1) pozycjonujący split w sezonie. SplitNumber (1..) ma priorytet
 * — stabilny, niezależny od dat playoffów; inaczej z etykiety splitu; inaczej z
 * miesiąca daty meczu (fallback). Razem z rokiem daje `splitOrder` = monotoniczną
 * oś x kariery (rok + ułamek), na której liczymy nachylenie trajektorii.
 */
export function splitFraction(
  splitNumber: number | null,
  split: string,
  month: number // 1..12 z daty meczu (fallback)
): number {
  if (splitNumber && splitNumber > 0) return Math.min((splitNumber - 1) * 0.3, 0.9);
  for (const k of KNOWN_SPLITS) if (k.label === split) return k.frac;
  const m = split.match(/\bSplit\s*([1-4])\b/i);
  if (m) return Math.min((Number(m[1]) - 1) * 0.3, 0.9);
  const byMonth = (month - 1) / 12;
  return Math.min(Math.max(byMonth, 0), 0.99);
}
