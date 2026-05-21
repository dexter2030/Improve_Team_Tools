"""
leagues.py — definicja presetów lig do scoutingu.

================== TO JEST JEDYNY PLIK DO RĘCZNEJ EDYCJI ==================
Podział lig zmienia się sezonowo (Riot przetasowuje ERL-e, ligi awansują
/spadają). Gdy scena się zmieni — popraw tylko ten plik, reszta modułu
się dostosuje automatycznie.

Nazwy lig muszą pasować (jako podciąg, bez rozróżniania wielkości liter)
do pola `ScoreboardGames.Tournament` w Leaguepedia oraz `league` w bazie
draftów. Pole bywa pełną nazwą turnieju ("LEC 2025 Summer"), dlatego
trzymamy krótkie nazwy ("LEC", "LFL").

ROZDZIELANIE DYWIZJI / KOLIZJE NAZW: "LFL" jest podciągiem
"LFL Division 2", a "LPL" — podciągiem "LPLOL". Samo dopasowanie po
podciągu zlałoby te ligi. Funkcja more_specific() zwraca dłuższe znane
nazwy zawierające daną nazwę; warstwy dopasowania (leaguepedia, db,
analyzer) je wykluczają, więc każda liga łapie wyłącznie własne mecze.
"""

# --- pojedyncze grupy lig (klocki, z których budujemy presety) ---

# Tier 1 = major regiony RAZEM z wydarzeniami międzynarodowymi
TIER1 = ["LEC", "LCK", "LPL", "LCS", "MSI", "Worlds", "First Stand"]

# ERL-e — pierwsze dywizje (najwyższy poziom ligi regionalnej).
# Skróty pasujące do pola Tournament w Leaguepedia: PRM = Prime League
# (Niemcy; tamtejsze turnieje mają numer dywizji w nazwie, stąd wpis
# "PRM 1st Division"), LVP SL = LVP SuperLiga (Hiszpania), GLL = liga
# grecka, EBL = Esports Balkan League, PG Nationals = liga włoska,
# LPLOL = liga portugalska.
ERL_D1 = [
    "LFL", "PRM 1st Division", "LVP SL", "TCL", "NLC", "Rift Legends",
    "PG Nationals", "Arabian League", "GLL", "LPLOL", "Hitpoint Masters",
    "EBL", "Road of Legends",
]

# ERL-e — drugie dywizje. Tylko ligi, które faktycznie mają osobną drugą
# dywizję na Leaguepedia (sprawdzone). Nazwa to dokładny podciąg turnieju
# 2. dywizji. Pierwsza dywizja danej ligi (np. "LFL") wyklucza te nazwy
# przez more_specific(), więc dywizje się nie mieszają.
ERL_D2 = [
    "LFL Division 2", "PRM 2nd Division", "LVP SL 2nd Division",
    "TCL Division 2", "NLC 2nd Division", "Arabian League 2nd Division",
    "LPLOL 2nd Div",
]


# --- SZYBKIE PRESETY ---
# Klikalne skróty, które wypełniają multiselect lig. Po wybraniu presetu
# listę lig nadal można dowolnie edytować ręcznie. Presety są kumulatywne,
# ale to tylko wygoda — multiselect pozostaje w pełni swobodny.

PRESETS: dict[str, list[str]] = {
    "Tier 1 — major + MSI/Worlds":
        TIER1,
    "+ ERL-e (pierwsze dywizje)":
        TIER1 + ERL_D1,
    "Wszystkie ligi (z drugimi dywizjami)":
        TIER1 + ERL_D1 + ERL_D2,
}

# preset użyty do wstępnego wypełnienia multiselecta przy starcie
DEFAULT_PRESET = "Tier 1 — major + MSI/Worlds"


# --- GRUPY LIG (dla zakładki Database) ---
# Te same klocki co presety, tylko rozbite na sekcje statusu bazy.
# Etykieta sekcji -> lista lig; kolejność = kolejność sekcji w zakładce.
LEAGUE_GROUPS: dict[str, list[str]] = {
    "Tier 1 — major i wydarzenia międzynarodowe": TIER1,
    "ERL — pierwsze dywizje (ERL 1)": ERL_D1,
    "ERL — drugie dywizje (ERL 2)": ERL_D2,
}


def all_known_leagues() -> list[str]:
    """Płaska lista wszystkich lig zdefiniowanych w presetach (bez duplikatów)."""
    seen, out = set(), []
    for leagues in PRESETS.values():
        for lg in leagues:
            if lg not in seen:
                seen.add(lg)
                out.append(lg)
    return out


def more_specific(league: str) -> list[str]:
    """Znane nazwy lig, które zawierają `league` jako podciąg (i nie są nią).

    Używane do rozdzielania dywizji i kolizji nazw: dopasowując ligę X
    trzeba wykluczyć turnieje pasujące do bardziej szczegółowej nazwy Y
    (np. X="LFL" -> Y="LFL Division 2"; X="LPL" -> Y="LPLOL"), inaczej
    X połknąłby mecze Y. Porównanie ignoruje wielkość liter.
    """
    low = league.lower()
    return [lg for lg in all_known_leagues()
            if lg.lower() != low and low in lg.lower()]
