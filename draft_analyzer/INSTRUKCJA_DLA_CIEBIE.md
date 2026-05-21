# INSTRUKCJA DLA CIEBIE — uruchomienie projektu scoutingowego

Ten dokument mówi Ci **gdzie wrzucić pliki i co kliknąć**. Drugi dokument
(`BRIEF_DLA_CLAUDE_CODE.md`) jest dla Claude Code — wkleisz mu go
w terminalu, a on zbuduje resztę.

Twój projekt scoutingowy dopiero powstaje, więc tu zaczynamy od zera.
Draft Analyzer będzie jego pierwszą zakładką — Claude Code zbuduje wokół
niego szkielet aplikacji, gotowy na kolejne zakładki w przyszłości.

---

## Co dostałeś

Katalog `draft_analyzer/` z gotowym, przetestowanym modułem analizy
draftów (pick & ban):

| Plik | Co robi |
|------|---------|
| `analyzer.py` | Silnik analizy draftów |
| `db.py` | Baza SQLite na drafty |
| `leaguepedia.py` | Pobieranie danych z Leaguepedia |
| `leagues.py` | Lista lig i presety |
| `draft_analyzer_page.py` | Zakładka (interfejs Streamlit) |
| `README.md` | Opis techniczny modułu |

---

## KROK 1 — Utwórz folder projektu

Zrób na dysku pusty folder na cały projekt scoutingowy, np.:

```
lol-scouting/
```

Wejdź do niego. To będzie katalog główny — wszystko inne powstaje w środku.

---

## KROK 2 — Wrzuć moduł do folderu

Skopiuj **cały katalog `draft_analyzer/`** do środka folderu projektu.
Po tym kroku masz:

```
lol-scouting/
└── draft_analyzer/
    ├── analyzer.py
    ├── db.py
    ├── leaguepedia.py
    ├── leagues.py
    ├── draft_analyzer_page.py
    └── README.md
```

Tylko tyle. Główny plik aplikacji, zakładki, struktura — to wszystko
zbuduje Claude Code w kroku 4.

---

## KROK 3 — Zainstaluj Pythona i zależności

1. Upewnij się, że masz **Pythona 3.10 lub nowszego**
   (sprawdź: `python --version`).
2. Otwórz terminal w folderze `lol-scouting/` i wpisz:

   ```
   pip install streamlit requests
   ```

   Jeśli używasz wirtualnego środowiska — najpierw je utwórz i aktywuj,
   potem instaluj. (Claude Code i tak zaproponuje Ci `venv` w kroku 4,
   jeśli go nie masz.)

---

## KROK 4 — Uruchom Claude Code

W terminalu, **w folderze `lol-scouting/`**, uruchom:

```
claude
```

Otwórz plik `BRIEF_DLA_CLAUDE_CODE.md`, skopiuj **całą jego treść**
i wklej jako pierwszą wiadomość. Claude Code:

1. zbuduje szkielet aplikacji Streamlit (główny plik + struktura zakładek),
2. wepnie Draft Analyzer jako pierwszą zakładkę,
3. poprawi importy modułu, by działały w nowej strukturze,
4. doda nowe funkcje (wykresy, eksport, statystyki),
5. powie Ci, co zrobił i jak uruchomić.

Odpowiadaj na jego pytania — szczegóły modułu zna z briefu.

---

## KROK 5 — Pierwsze uruchomienie

Gdy Claude Code skończy, uruchom aplikację (poda Ci dokładną komendę,
prawdopodobnie):

```
streamlit run app.py
```

W przeglądarce:

1. Wejdź w zakładkę **Draft Analyzer**.
2. Rozwiń sekcję **„⚙️ Dane — pobierz drafty z Leaguepedia"**.
3. Wpisz ligę (np. `LEC`) i kliknij **Pobierz dane**. Pierwsze
   pobranie może potrwać minutę-dwie.
4. Powtórz dla innych lig (`LCK`, `LPL`, `LCS`...).
5. Gdy baza ma dane — wpisz bany, ustaw suwak, wybierz ligi, analizuj.

---

## Na co zwrócić uwagę

- **Pierwsze pobranie zwróciło 0 gier?** Nazwy kolumn w Leaguepedia
  bywają zmieniane. Powiedz to Claude Code — w briefie ma instrukcję,
  jak to naprawić.
- **Podział lig na „topowe ERL-e" Ci nie pasuje?** Otwórz
  `draft_analyzer/leagues.py` i popraw listy `TIER1`, `ERL_TOP`,
  `ERL_REST` na samej górze pliku. To zwykłe listy nazw — nie trzeba
  znać Pythona.
- **Kolejne zakładki w przyszłości** (np. profile graczy, statystyki
  drużyn) — Claude Code zbuduje szkielet tak, żeby dało się je dokładać
  bez przebudowy. Gdy będziesz gotów, po prostu poproś go o nową zakładkę.

---

## Szybka checklista

- [ ] Folder projektu utworzony
- [ ] Katalog `draft_analyzer/` wrzucony do środka
- [ ] Python 3.10+ oraz `pip install streamlit requests` zrobione
- [ ] Claude Code uruchomiony, brief wklejony
- [ ] Aplikacja wstaje po `streamlit run`
- [ ] Zakładka Draft Analyzer działa
- [ ] Dane pobrane z Leaguepedia (min. jedna liga)
- [ ] Analiza zwraca wyniki
