# BRIEF DLA CLAUDE CODE — budowa projektu scoutingowego LoL

Jesteś w pustym (lub prawie pustym) folderze nowego projektu — narzędzia
do scoutingu graczy League of Legends, w **Streamlit**. Jedyne, co tu
jest, to katalog `draft_analyzer/` z gotowym, przetestowanym modułem
analizy draftów (pick & ban).

Twoje zadanie ma trzy części:
  A. Zbudować szkielet aplikacji Streamlit od zera.
  B. Wpiąć Draft Analyzer jako pierwszą zakładkę.
  C. Rozbudować moduł o nowe funkcje (wykresy, eksport, statystyki).

NIE przepisuj modułu `draft_analyzer/` od zera — jest przetestowany.
Masz go zintegrować i rozszerzyć, nie zastąpić.

---

## 0. Najpierw rozpoznanie

1. Wylistuj zawartość folderu projektu.
2. Przeczytaj **w całości** `draft_analyzer/README.md` — opisuje, jak
   moduł działa: drzewo prawdopodobieństw (bany → Blue Pick 1 → Red
   Pick 1/2), suwak dopasowania banów, presety lig.
3. Przejrzyj pliki modułu, żeby zrozumieć interfejsy:
   - `draft_analyzer_page.py` — funkcja `render()` renderuje całą zakładkę.
   - `analyzer.py` — funkcja `analyze(...)`, czysta logika.
   - `db.py` — baza SQLite, `init_db()` / `upsert_draft()` / `fetch_all_drafts()`.
   - `leaguepedia.py` — pobieranie danych, `fetch_drafts(...)`.
   - `leagues.py` — presety lig (`PRESETS`, `TIER1`, `ERL_TOP`, `ERL_REST`).
4. Sprawdź wersję Pythona i czy istnieje środowisko wirtualne.

Streść mi ustalenia, potem przejdź dalej.

---

## CZĘŚĆ A — Szkielet aplikacji Streamlit

Zbuduj minimalną, czystą strukturę projektu. Cel: aplikacja, do której
łatwo dokładać kolejne zakładki (w przyszłości m.in. profile graczy,
statystyki drużyn — teraz ich NIE buduj, tylko nie zamykaj na nie drogi).

Proponowana struktura (dostosuj, jeśli masz lepszy pomysł — uzasadnij):

```
lol-scouting/
├── app.py                  # główny plik — st.set_page_config + nawigacja
├── requirements.txt        # streamlit, requests (+ to, co dodasz)
├── README.md               # krótki opis projektu i jak uruchomić
├── .gitignore              # venv, __pycache__, *.db, .streamlit/secrets
└── draft_analyzer/         # istniejący moduł (już jest)
    └── ...
```

Wymagania dla `app.py`:
- `st.set_page_config(...)` z sensownym tytułem i ikoną.
- Nawigacja między zakładkami. Użyj **`st.navigation` / `st.Page`**
  (nowoczesne API multipage) ALBO `st.sidebar` z `st.radio` — wybierz
  jedno, zrób spójnie. Ma być oczywiste, gdzie dodać następną zakładkę.
- Na razie jedna pozycja: „Draft Analyzer". Dodaj komentarz-placeholder
  pokazujący, jak dopiąć kolejną.
- Wygeneruj `requirements.txt` z realnymi zależnościami.
- Jeśli nie ma środowiska wirtualnego — zaproponuj `venv` i podaj komendy.

---

## CZĘŚĆ B — Wpięcie zakładki Draft Analyzer

1. Punkt wejścia modułu to funkcja `render()` w
   `draft_analyzer/draft_analyzer_page.py` — wywołanie jej renderuje
   całą zakładkę.
2. Podłącz `render()` do nawigacji z części A.
3. **Napraw importy.** Pliki modułu importują się obecnie płasko
   (`from analyzer import ...`, `from db import ...` itd.). Po wpięciu
   do projektu jako pakiet `draft_analyzer` te importy się posypią.
   Ujednolić je do pakietowych, np. `from draft_analyzer.analyzer
   import analyze`, ALBO zastosuj inny spójny mechanizm — byle
   konsekwentnie we wszystkich plikach modułu. Dodaj
   `draft_analyzer/__init__.py`, jeśli trzeba.
   Importy do sprawdzenia są w: `draft_analyzer_page.py` (importuje
   `db`, `analyzer`, `leaguepedia`, `leagues`).
4. Baza danych: moduł ma własną bazę SQLite i **tak ma zostać** —
   nie podpinaj go do żadnej innej bazy. Zwróć tylko uwagę, gdzie
   powstanie plik `drafts.db` (`DB_PATH` w `db.py`) — niech trafi
   w sensowne miejsce, np. `data/drafts.db`; jeśli zmienisz ścieżkę,
   upewnij się, że katalog istnieje i jest w `.gitignore`.

Po części B aplikacja musi wstawać i pokazywać działającą zakładkę.

---

## CZĘŚĆ C — Nowe funkcje

Dodaj poniższe do zakładki Draft Analyzer. Trzymaj logikę obliczeniową
w `analyzer.py` (czyste funkcje), a samo rysowanie w warstwie UI —
nie mieszaj.

1. **Wykres rozkładu picków.** Zamiast (lub obok) pasków `st.progress`
   dodaj wykres słupkowy rozkładu Blue Pick 1 oraz odpowiedzi Red.
   Użyj wbudowanego `st.bar_chart` albo Altair — bez ciężkich
   zależności, jeśli nie trzeba.

2. **Eksport wyników do CSV.** Przycisk `st.download_button`, który
   zapisuje aktualny wynik analizy (rozkład B1 i odpowiedzi Red, wraz
   z liczbami i procentami) do pliku CSV.

3. **Statystyki dodatkowe.** Rozszerz wynik `analyze()` o:
   - win rate poszczególnych championów na Blue Pick 1 (jeśli dane
     o zwycięzcy pozwalają),
   - liczbę unikalnych drużyn w próbie (czy wzorzec to trend wielu
     zespołów, czy upodobanie jednego),
   - rozkład patchy w próbie (czy dane nie są przestarzałe).
   Pokaż je w UI zwięźle, nie zaśmiecając widoku.

4. **Filtr po drużynie (opcjonalny).** Pole wyboru drużyny — gdy
   ustawione, analiza pokazuje, co dana drużyna pickuje na blue side
   w dopasowanych draftach. Przydatne do scoutingu konkretnego
   przeciwnika. Jeśli to za duży zakres na teraz — zostaw zaczepienie
   w kodzie (TODO) i zapytaj mnie.

Po każdej funkcji sprawdzaj, że aplikacja nadal wstaje bez błędu.

---

## Weryfikacja — obowiązkowa

1. Wszystkie pliki kompilują się: `python -m py_compile` na każdym
   pliku `.py` w projekcie.
2. `streamlit run app.py` startuje bez czerwonego tracebacku.
3. Zakładka Draft Analyzer otwiera się, renderują się: sekcja
   pobierania danych, pola banów, suwak, wybór lig, nowe wykresy
   i przycisk eksportu.
4. NIE musisz pobierać prawdziwych danych z Leaguepedia w teście
   (wymaga sieci, trwa). Aby sprawdzić logikę bez sieci: wygeneruj
   kilkadziesiąt sztucznych draftów, włóż przez `db.upsert_draft()`,
   potwierdź że `analyze()` i wykresy działają, potem usuń dane testowe.

---

## Znany problem — Leaguepedia API

Jeśli przy pobieraniu danych moduł zwróci 0 gier: nazwy kolumn w tabeli
Cargo `PicksAndBansS7` bywają zmieniane przez wiki. Sprawdź wtedy
aktualny schemat pod adresem w nagłówku `leaguepedia.py` i popraw nazwy
pól w funkcji `_normalize()` oraz w zapytaniu. Nie zgaduj — zweryfikuj
ze schematem.

---

## Zasady pracy

- Po rozpoznaniu (sekcja 0) **zatrzymaj się i pokaż mi ustalenia**
  oraz proponowaną strukturę projektu, zanim zaczniesz tworzyć pliki.
- Rób części po kolei: A → B → C. Po każdej części sprawdź, że
  aplikacja wstaje, i krótko mnie poinformuj.
- Nie zmieniaj logiki w `analyzer.py` w sposób, który psuje istniejące
  funkcje — tylko dodawaj. Presetów w `leagues.py` nie ruszaj.
- Trzymaj kod czysty: logika obliczeniowa osobno od UI, sensowne nazwy,
  komentarze po polsku (spójnie z modułem).
- Pisz tak, by dało się łatwo dodać kolejne zakładki — to dopiero
  początek projektu scoutingowego.
- Na koniec streść: co powstało, jak uruchomić aplikację, gdzie dodać
  następną zakładkę.

---

## Co będzie dalej (kontekst, NIE rób tego teraz)

Projekt docelowo dostanie kolejne zakładki — profile graczy, statystyki
drużyn, historia meczów. Dlatego szkielet z części A ma być otwarty na
rozbudowę. Tych zakładek na razie NIE buduj — skup się na A, B, C.
