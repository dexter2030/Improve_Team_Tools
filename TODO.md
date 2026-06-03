# TODO

Lista rzeczy do zrobienia / weryfikacji wokół Cohort Baseline i SoloQ Lookup.
Pogrupowane po pilności. Najświeższe rzeczy są na górze każdej sekcji.

> **Stan na 2026-06-01:** refaktor monorepo (P1–P6) oraz porównanie do
> kohorty (per-region / champion / Z-score) są zmergowane do `main`
> (PR #13, #14). Szczegóły w sekcji „Zrobione" na dole — odhaczone tam
> pozycje są zweryfikowane w kodzie.

## Pilne — manualny smoke test produkcji

Wymaga człowieka w przeglądarce po deployu; nie da się odhaczyć z poziomu
testów. Najważniejszy jest pierwszy scrape lolpros (zob. Znane ryzyka).

- [ ] Otworzyć production (`improve-team-tools.vercel.app`) po deployu i
      sprawdzić, czy w sidebarze widać **SoloQ Lookup** i **Cohort Baseline**.
- [ ] **SoloQ Lookup**: wpisać `BIN fanboy#qubzx` / `euw1` → fetch musi
      zwrócić rangę, listę championów i tabelę meczy bez błędów.
- [ ] **Cohort Baseline → sekcja 1 (Scrape lolpros)**: na 5 graczach
      sprawdzić, czy zwraca konta (jeśli wszędzie `0 accounts` — schemat
      NEXT_DATA się zmienił, parser w `lolpros.py`
      `scrape_lolpros_accounts` wymaga korekty).
- [ ] **Cohort Baseline → sekcja 2 (Compute baseline)**: ustawić limit
      na 10 kont, odpalić, sprawdzić, czy raport końcowy ma niezerowe
      „saved" i czy w sekcji 3 widać dodane wiersze.
- [ ] **SoloQ Lookup → Compare against cohort**: po zbudowaniu kohorty
      wracamy do tego samego gracza i sprawdzamy, czy percentyle/Z-score
      się renderują.

## Znane ryzyka

- **Parser lolpros NEXT_DATA** — schemat strony lolpros.gg może być inny
  niż założyłem. `scrape_lolpros_accounts` toleruje kilka aliasów
  (`game_name`/`name`/`summoner_name`, `server`/`region`/`rgn`...), ale
  jeśli pole zostało przesunięte głębiej albo zmieniono nazwy, scrape
  zwróci pustą listę. Plan B: log raw `__NEXT_DATA__` z 1 strony i
  dopasować parser do aktualnego schematu.
- **Rate limit Riot API** przy pełnej kohorcie. ~750 graczy × ~2 konta
  × (1 resolve + 1 ranked + ~5 strony match IDs + ~50 meczy + ~50 timeline)
  ≈ 80k callów. Z production key (rate limit zazwyczaj 500/10s, 30k/10min)
  to nadal kilka godzin. Sekcja 2 w UI ma „Limit to N accounts" — odpalać
  w batchach.
- **Streamlit blokuje UI podczas batch fetch.** Zamknięta przeglądarka =
  przerwany fetch (cache zostaje, więc retry kontynuuje). Do rozważenia
  background worker (zob. Ulepszenia — workflow).

## Ulepszenia — comparison quality

- [ ] **Split-over-split delta.** Drugi cutoff w `soloq_baseline` (każdy
      gracz może mieć N wpisów per cutoff) → pokazać, czy gracz rośnie
      (delta KDA, CS/min, GD@15 między splitami). Wymaga zmian w
      `src/processing/comparison.py` + UI w „Compare against cohort".

## Ulepszenia — workflow

- [ ] **Background job dla batch baseline.** Streamlit nie nadaje się do
      wielogodzinnego fetchu. Rozważyć: prosty CLI script
      `python -m scripts.fetch_cohort --leagues TIER1 --since 2026-01-01`
      odpalany z cron / GitHub Actions, zapisujący do tego samego SQLite.
- [ ] **Notes per cohort entry.** Coach może chcieć dopisać uwagi do
      gracza w kohorcie („sprawdzony, młodszy niż wygląda"). Dodać
      kolumnę `notes` w `soloq_baseline` + edit-in-place.
- [ ] **Eksport baseline do CSV.** W sekcji „Browse cohort" przycisk
      download — dla shareowania z innymi coachami.
- [ ] **Auto-refresh „aktywnych" graczy.** Cron daily fetch dla graczy z
      ostatnimi meczami < 7 dni temu (nie potrzeba pełnego rebuildu).

## Ulepszenia — UX

- [ ] **Preset cutoff sezonu.** Zamiast date_input z domyślną 1.1.2026 —
      dropdown z preset'ami („Spring 2026", „Summer 2026", „Last 90 days",
      „Custom..."). Ten domyślny i tak będzie się starzeć.
- [ ] **„Bulk add to Scouting" z kohorty.** Gracze z kohorty z wysokim
      Z-score na ich roli powinni być easy-to-add do listy scoutingu
      (jeden klik per wiersz w „Browse cohort").
- [ ] **Champion-icon column w pool table.** SoloQ Lookup champion pool
      pokazuje tylko nazwy (`_render_champion_section`) — ikona championa
      szybsza do skanowania.

## Tech debt / sprzątanie

- [ ] **Lolpros account scraping** — pełne pobranie HTML każdej strony.
      Można dodać `If-Modified-Since` i cache po `Last-Modified` —
      drugi scrape tego samego gracza byłby tańszy.
- [ ] **`.next/` i `.vscode/` w roocie repo** — wiszą jako nieśledzone.
      `.next/` to build Next.js (apps/web), powinien iść do `.gitignore`.

## Zrobione (zweryfikowane w kodzie, 2026-06-01)

- [x] **Per-region kohorty** — `region_for_platform` + filter region w
      „Compare against cohort" (`app/soloq_lookup_page.py`,
      `src/processing/comparison.py`). KR i EU porównywane osobno.
- [x] **Champion-specific comparison** — `filter_matches_by_champion`
      w `src/processing/soloq_aggregates.py` + filtr championa w UI.
- [x] **Visualization Z-score bar chart** — `z_score_sentiment`
      (diverging bar chart, zielone w prawo / czerwone w lewo).
- [x] **Unit testy** dla `comparison.py`, `soloq_aggregates.py`,
      `cohort_baseline.py` (+ `test_lolpros.py`, `test_match_ids.py`)
      w `apps/streamlit-dashboard/tests/`.
- [x] **Match IDs cache TTL** — osobny `_MATCH_IDS_ARCHIVE_TTL` (24h) dla
      zapytań z `start_time` (lista sezonowa jest stabilna), krótki
      15-min TTL został dla live lookup (`packages/shared/.../riot_client.py`).
- [x] **Kohorta w osobnej bazie** — podział baz per domena
      (profiles/cache/drafts/players/cohort.db); kohorta nie dzieli już
      pliku z draftami (P3, `src/paths.py`).
- [x] **Refaktor monorepo (kontekst)** — `apps/` + `packages/shared`,
      centralizacja ścieżek DB, równoległy fetch meczy + batch upsert (P1–P6).
