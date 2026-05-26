# TODO

Lista rzeczy do zrobienia / weryfikacji wokół Cohort Baseline i SoloQ Lookup.
Pogrupowane po pilności. Najświeższe rzeczy są na górze każdej sekcji.

## Pilne — smoke test po merge PR #6

- [ ] Otworzyć production (`improve-team-tools.vercel.app`) po deployu i
      sprawdzić, czy w sidebarze widać **SoloQ Lookup** i **Cohort Baseline**.
- [ ] **SoloQ Lookup**: wpisać `BIN fanboy#qubzx` / `euw1` → fetch musi
      zwrócić rangę, listę championów i tabelę meczy bez błędów.
- [ ] **Cohort Baseline → sekcja 1 (Scrape lolpros)**: na 5 graczach
      sprawdzić, czy zwraca konta (jeśli wszędzie `0 accounts` — schemat
      NEXT_DATA się zmienił, parser w `draft_analyzer/lolpros.py`
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
  background worker (zob. Ulepszenia poniżej).

## Ulepszenia — comparison quality

- [ ] **Per-region kohorty.** KR vs EU mają zupełnie inny meta (CS/min,
      gold/min). Z-score liczony globalnie krzywdzi/faworyzuje
      regiony. Dodać filter region (na bazie kolumny `platform` w
      `soloq_baseline`) w sekcji „Compare against cohort".
- [ ] **Champion-specific comparison.** Scoutowanie midlanera grającego
      głównie Ahri — porównanie do kohorty „wszyscy midi" zaszumione.
      Możliwość: filter „same champion as player's most-played" + Z-score
      vs kohorta tego championa.
- [ ] **Split-over-split delta.** Drugi cutoff w `soloq_baseline` (każdy
      gracz może mieć N wpisów per cutoff) → pokazać, czy gracz rośnie
      (delta KDA, CS/min, GD@15 między splitami).
- [ ] **Visualization Z-score bar chart.** W „Compare against cohort"
      poziomy bar chart Z-score per metryka (zielone w prawo, czerwone w
      lewo) — szybsze do skanowania niż tabela.

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
      pokazuje tylko nazwy — ikona championa szybsza do skanowania.

## Tech debt / sprzątanie

- [ ] **Unit testy** dla `src/processing/comparison.py`,
      `src/processing/soloq_aggregates.py`, `src/processing/cohort_baseline.py`.
      Wzorzec: `tests/test_ranked.py`, `tests/test_champion_stats.py`.
- [ ] **Match IDs cache TTL** — 15 min globalnie OK dla SoloQ Lookup, ale
      dla baseline (rebuild raz na tydzień) za krótki, każdy refetch
      idzie do API. Osobny dłuższy TTL dla zapytań z `start_time` byłby
      bezpieczny (tamte ID nie znikają).
- [ ] **DB.path =** `draft_analyzer/drafts.db` (kohorta dzieli plik z
      draftami). Spójniej byłoby trzymać kohortę w `scouting.db` razem
      z profilami i cache'em API. Wymaga migracji.
- [ ] **Lolpros account scraping** — pełne pobranie HTML każdej strony.
      Można dodać `If-Modified-Since` i cache po `Last-Modified` —
      drugi scrape tego samego gracza byłby tańszy.
