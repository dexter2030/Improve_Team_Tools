# Draft Analyzer — moduł scoutingowy (Streamlit)

Zakładka do analizy historycznych draftów League of Legends. Na podstawie
kombinacji banów pokazuje najczęstsze **Blue Pick 1**, a po wybraniu picka —
najczęstsze odpowiedzi **Red Pick 1 i Red Pick 2**.

## Pliki

| Plik | Rola | Zależny od frameworka? |
|------|------|------------------------|
| `analyzer.py` | Silnik analizy (drzewo prawdopodobieństw) | nie |
| `db.py` | Tabela `drafts` w SQLite + zapis/odczyt | nie |
| `leaguepedia.py` | Pobieranie draftów z Leaguepedia Cargo API | nie |
| `leagues.py` | Definicja presetów lig — **plik do ręcznej edycji** | nie |
| `draft_analyzer_page.py` | Zakładka Streamlit (UI) | tak — Streamlit |

## Zakres lig — `leagues.py`

W zakładce wybór lig to **swobodny multiselect** — dodajesz i usuwasz
dowolne ligi. Nad nim są **szybkie presety** (przyciski), które wypełniają
multiselect jednym kliknięciem; po wybraniu presetu listę nadal można
dowolnie edytować.

`leagues.py` to jedyny plik do ręcznej edycji. Definiuje trzy presety:

1. **Tier 1 — major + MSI/Worlds** (LEC, LCK, LPL, LCS, MSI, Worlds,
   First Stand)
2. **+ topowe ERL-e** — dochodzą ligi akredytowane (LFL, Prime League,
   Superliga/Hispania, TCL)
3. **Wszystkie ligi** — dochodzą nieakredytowane ERL-e (NLC, Rift
   Legends, LIT, Arabian League itd.)

Podział akredytowane/nieakredytowane odpowiada sezonowi 2025. Riot
przetasowuje ERL-e co sezon — gdy się zmieni, popraw słowniki `TIER1`,
`ERL_TOP`, `ERL_REST` na górze `leagues.py`. Reszta modułu dostosuje
się automatycznie.

Zakres lig **nie rozszerza się sam** — przy małej próbie zakładka tylko
neutralnie podpowiada, że można dodać ligi, ale decyzję podejmujesz Ty.

## Integracja z istniejącym projektem Streamlit

Skopiuj pliki do projektu, potem wybierz jeden z dwóch sposobów wpięcia:

**Opcja A — projekt multipage (katalog `pages/`)**

Wrzuć `draft_analyzer_page.py` do katalogu `pages/`, np. jako
`pages/4_Draft_Analyzer.py`. Streamlit automatycznie doda zakładkę
w menu bocznym. Pliki silnika (`analyzer.py`, `db.py`, `leaguepedia.py`)
muszą być importowalne — najprościej obok, w katalogu głównym projektu.

**Opcja B — własny system zakładek (`st.tabs`, `st.radio` itp.)**

```python
from draft_analyzer_page import render

tab1, tab2, tab_draft = st.tabs(["Gracze", "Drużyny", "Draft Analyzer"])
with tab_draft:
    render()
```

Zależności:

```bash
pip install streamlit requests
```

## Pierwsze uruchomienie — załadowanie danych

Baza startuje pusta. W zakładce rozwiń sekcję **„⚙️ Dane — pobierz drafty
z Leaguepedia"**, wpisz ligę (np. `LEC`) i kliknij *Pobierz dane*.
Powtórz dla innych lig. Operacja jest idempotentna (`upsert` po
`match_id`), więc można ją uruchamiać wielokrotnie do odświeżania.

## Jak działa suwak dopasowania

Suwak (3–6) decyduje, ile z 6 banów musi się pokrywać, żeby gra trafiła
do próby. Bany traktowane są jako **zbiór** — strona i kolejność nie mają
znaczenia.

- **6/6** — drafty rzadko powtarzają się 1:1, próba będzie minimalna.
- **3/6** — duża próba, luźniejsze podobieństwo.

Jeśli przy ustawionym progu próba jest za mała (`< min_sample`), silnik
sam obniża próg o 1 (aż do 3) i zaznacza to ostrzeżeniem nad wynikami.

## Przepływ użytkownika w zakładce

1. Wpisz bany (do 6) i ustaw suwak dopasowania.
2. *Analizuj draft* → lista najczęstszych Blue Pick 1 z procentami.
3. Wybierz Blue Pick 1 → pojawiają się rozkłady Red Pick 1 i Red Pick 2
   plus win rate blue dla tej linii draftu.

## Uwagi

- Nazwy kolumn w tabeli Cargo `PicksAndBansS7` bywają zmieniane przez wiki.
  Jeśli pobieranie zwróci 0 gier, sprawdź aktualny schemat:
  https://lol.fandom.com/wiki/Special:CargoTables/PicksAndBansS7
- Konwencja stron w `leaguepedia.py`: Team1 = blue, Team2 = red.
  Warto zweryfikować na kilku znanych meczach po pierwszym pobraniu.
- Przy małej próbie (`n < 10`) statystyki są poglądowe — UI zawsze
  pokazuje liczbę gier, żeby było widać wielkość próby.
- SQLite jest tu optymalny: drafty zawodowe to maks dziesiątki tysięcy
  rekordów. Podmiana na PostgreSQL = zmiana connection stringu w `db.py`,
  reszta modułu jest niezależna od bazy.
- Jeśli Twój projekt ma już własną bazę meczów, można pominąć `db.py`
  i przepiąć `draft_analyzer_page.py` na istniejące źródło danych —
  silnik `analyzer.py` przyjmuje zwykłą listę słowników.
