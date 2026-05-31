"""
analyzer.py — silnik wyszukiwania draftów.

Wyszukiwarka po wzorcu pick&ban: podajesz championów w slotach (strona
blue/red, kategoria pick/ban), a silnik zwraca drafty, które ten wzorzec
spełniają. Dwa różne tryby dopasowania:

  * Picki — pozycyjnie: slot N w UI musi być N-tym pickiem draftu po
    odpowiedniej stronie. Wpisanie Wukonga w 1. slocie pick Blue znajduje
    tylko drafty, w których Blue side faktycznie pickowało Wukonga jako
    pierwszego (b1_pick), a nie gdziekolwiek wśród swoich pięciu picków.
  * Bany — pulowo, bez znaczenia strony, ale z podziałem faz: pierwsze 3
    sloty ban (zarówno Blue jak i Red) trafiają do puli „faza 1" (6 banów
    obu drużyn łącznie), a sloty 4-5 — do puli „faza 2" (4 bany łącznie).
    Wpisany ban musi znaleźć się w odpowiedniej puli, niezależnie od tego,
    która drużyna go zabanowała.

Porównanie ignoruje wielkość liter. Czyste funkcje, bez zależności od
Streamlita — warstwa UI siedzi w draft_analyzer_page.py.
"""

from collections import Counter

from .leagues import more_specific


def filter_by_leagues(drafts: list[dict],
                      allowed_leagues: list[str] | None) -> list[dict]:
    """
    Zawęża drafty do wybranych lig.

    `allowed_leagues` — lista nazw lig (jak w polu `league` draftu).
                        None lub pusta lista = bez filtra (wszystkie ligi).

    Dopasowanie jest tolerancyjne: pole `league` z Leaguepedia bywa pełną
    nazwą turnieju (np. "LEC 2024 Summer"), więc sprawdzamy, czy któraś
    z dozwolonych nazw występuje jako podciąg. Bardziej szczegółowe nazwy
    lig wykluczamy (leagues.more_specific), żeby „LFL" nie łapało
    „LFL Division 2" — spójnie z warstwą pobierania.
    """
    if not allowed_leagues:
        return drafts
    # (podciąg do trafienia, podciągi do wykluczenia) dla każdej ligi
    matchers = [
        (lg.lower(), [e.lower() for e in more_specific(lg)])
        for lg in allowed_leagues if lg
    ]
    out = []
    for d in drafts:
        league = (d.get("league") or "").lower()
        for inc, excls in matchers:
            if inc in league and not any(e in league for e in excls):
                out.append(d)
                break
    return out


def _norm(names: list[str] | None) -> set[str]:
    """Zbiór nazw championów: przycięte, małe litery, bez pustych."""
    return {n.strip().lower() for n in (names or []) if n and n.strip()}


def _clean(name: str | None) -> str:
    """Pojedyncza nazwa championa znormalizowana (pusty string = brak)."""
    return (name or "").strip().lower()


def _picks_positional_ok(want: list[str] | None,
                         draft: dict, prefix: str) -> bool:
    """
    Picki pozycyjnie: dla każdego niepustego slotu i-tego sprawdza, że
    draft ma dokładnie tego championa na pozycji `{prefix}{i+1}_pick`.
    Puste sloty = brak ograniczenia.
    """
    if not want:
        return True
    for i, name in enumerate(want):
        target = _clean(name)
        if not target:
            continue
        actual = _clean(draft.get(f"{prefix}{i + 1}_pick"))
        if actual != target:
            return False
    return True


def _phase_ban_pool(draft: dict, phase: str) -> set[str]:
    """
    Pula banów jednej fazy, sumowana między stronami.
    phase='phase1' -> sloty ban 1-3 obu drużyn (6 banów łącznie).
    phase='phase2' -> sloty ban 4-5 obu drużyn (4 bany łącznie).
    """
    bb = list(draft.get("blue_bans") or [])
    rb = list(draft.get("red_bans") or [])
    if phase == "phase1":
        return _norm(bb[:3] + rb[:3])
    if phase == "phase2":
        return _norm(bb[3:5] + rb[3:5])
    return set()


def _wanted_ban_pool(blue_bans: list[str] | None,
                     red_bans: list[str] | None,
                     phase: str) -> set[str]:
    """Bany żądane w danej fazie — zlepione z obu kolumn UI (Blue + Red)."""
    bb = list(blue_bans or []) + [""] * 5
    rb = list(red_bans or []) + [""] * 5
    if phase == "phase1":
        return _norm(bb[:3] + rb[:3])
    if phase == "phase2":
        return _norm(bb[3:5] + rb[3:5])
    return set()


def search_drafts(
    drafts: list[dict],
    *,
    blue_picks: list[str] | None = None,
    blue_bans: list[str] | None = None,
    red_picks: list[str] | None = None,
    red_bans: list[str] | None = None,
) -> list[dict]:
    """
    Zwraca drafty pasujące do wzorca pick&ban.

    Picki dopasowywane są pozycyjnie (slot N w UI = N-ty pick draftu
    po odpowiedniej stronie). Bany trafiają do puli wspólnej dla obu
    stron, osobno dla fazy 1 (sloty ban 1-3) i fazy 2 (sloty ban 4-5).

    Brak jakiegokolwiek kryterium -> pusta lista (pusty wzorzec to zwykle
    niewypełniony formularz, nie żądanie „zwróć wszystko").
    """
    want_phase1 = _wanted_ban_pool(blue_bans, red_bans, "phase1")
    want_phase2 = _wanted_ban_pool(blue_bans, red_bans, "phase2")
    has_pick_filter = any(
        _clean(n) for n in list(blue_picks or []) + list(red_picks or [])
    )
    if not (want_phase1 or want_phase2 or has_pick_filter):
        return []

    out: list[dict] = []
    for d in drafts:
        if (_picks_positional_ok(blue_picks, d, "b")
                and _picks_positional_ok(red_picks, d, "r")
                and want_phase1 <= _phase_ban_pool(d, "phase1")
                and want_phase2 <= _phase_ban_pool(d, "phase2")):
            out.append(d)
    return out


# --- sugestie dla pustych slotów --------------------------------------------
#
# Klucze grup sugestii odpowiadają nowej semantyce dopasowania:
#   bp0..bp4  -> Blue pick na pozycji 0..4 (b1_pick..b5_pick)
#   rp0..rp4  -> Red pick na pozycji 0..4 (r1_pick..r5_pick)
#   phase1_bans -> bany fazy 1, wspólna pula obu stron (po 3 na drużynę)
#   phase2_bans -> bany fazy 2, wspólna pula obu stron (po 2 na drużynę)

_PICK_GROUPS = tuple(f"bp{i}" for i in range(5)) + tuple(
    f"rp{i}" for i in range(5)
)
_BAN_GROUPS = ("phase1_bans", "phase2_bans")
_GROUPS = _PICK_GROUPS + _BAN_GROUPS


def _group_champions(draft: dict, group: str) -> list[str]:
    """
    Lista championów draftu w danej grupie sugestii. Dla picków zwraca
    jednoelementową listę z championem z tej dokładnie pozycji, dla
    banów — pulę całej fazy zsumowaną z obu stron.
    """
    if group.startswith("bp"):
        i = int(group[2:])
        champ = draft.get(f"b{i + 1}_pick")
        return [champ] if champ else []
    if group.startswith("rp"):
        i = int(group[2:])
        champ = draft.get(f"r{i + 1}_pick")
        return [champ] if champ else []
    if group == "phase1_bans":
        bb = list(draft.get("blue_bans") or [])
        rb = list(draft.get("red_bans") or [])
        return bb[:3] + rb[:3]
    if group == "phase2_bans":
        bb = list(draft.get("blue_bans") or [])
        rb = list(draft.get("red_bans") or [])
        return bb[3:5] + rb[3:5]
    return []


def _already_in_group(criteria: dict, group: str) -> set[str]:
    """Championy już wpisane przez użytkownika w tej grupie — pomijane w sugestiach."""
    if group.startswith("bp"):
        i = int(group[2:])
        return _norm([(criteria.get("blue_picks") or [""] * 5)[i:i + 1][0]])
    if group.startswith("rp"):
        i = int(group[2:])
        return _norm([(criteria.get("red_picks") or [""] * 5)[i:i + 1][0]])
    if group == "phase1_bans":
        return _wanted_ban_pool(
            criteria.get("blue_bans"), criteria.get("red_bans"), "phase1"
        )
    if group == "phase2_bans":
        return _wanted_ban_pool(
            criteria.get("blue_bans"), criteria.get("red_bans"), "phase2"
        )
    return set()


def suggest_all(
    drafts: list[dict],
    criteria: dict,
) -> tuple[int, dict[str, list[dict]]]:
    """
    Liczy sugestie championów dla każdej grupy slotów osobno.

    `criteria` — wzorzec wpisany w siatce: dict z kluczami blue_picks /
                 blue_bans / red_picks / red_bans (listy nazw championów,
                 jak argumenty search_drafts).

    Najpierw wybiera drafty pasujące do `criteria`, a potem dla każdej
    grupy (pozycja pickowa lub faza banów) liczy, którzy championowie tam
    wystąpili. Zwraca krotkę (liczba_pasujących, sugestie) — `sugestie` to
    dict klucz_grupy -> lista {champion, count, pct} (`pct` jako udział
    pasujących draftów). Championowie już wpisani w danej grupie pomijani.
    """
    matches = search_drafts(
        drafts,
        blue_picks=criteria.get("blue_picks"),
        blue_bans=criteria.get("blue_bans"),
        red_picks=criteria.get("red_picks"),
        red_bans=criteria.get("red_bans"),
    )
    total = len(matches)
    suggestions: dict[str, list[dict]] = {}
    for group in _GROUPS:
        if total == 0:
            suggestions[group] = []
            continue
        already = _already_in_group(criteria, group)
        counter: Counter = Counter()
        for d in matches:
            for champ in _group_champions(d, group):
                name = (champ or "").strip()
                if name and name.lower() not in already:
                    counter[name] += 1
        suggestions[group] = [
            {"champion": champ, "count": n,
             "pct": round(100 * n / total, 1)}
            for champ, n in counter.most_common()
        ]
    return total, suggestions


# --- statystyki agregatowe --------------------------------------------------

def phase1_ban_stats(drafts: list[dict], top_n: int = 10) -> dict:
    """
    Najczęściej banowani championi w fazie 1 (sloty ban 1-3) z podziałem
    na stronę draftu.

    Faza 1 to 6 pierwszych banów meczu — po 3 z każdej strony. Rozdzielamy
    je per side, bo strona jest istotną cechą banu (Blue i Red mają różne
    priorytety i nie chodzi o pulę wspólną tak jak w wyszukiwarce).

    Zwraca {"blue": [...], "red": [...], "total": N}, gdzie listy to
    top_n championów: {champion, count, pct}. `pct` to udział draftów,
    w których champion znalazł się w pierwszych 3 banach danej strony.
    """
    blue: Counter = Counter()
    red: Counter = Counter()
    for d in drafts:
        for champ in (d.get("blue_bans") or [])[:3]:
            name = (champ or "").strip()
            if name:
                blue[name] += 1
        for champ in (d.get("red_bans") or [])[:3]:
            name = (champ or "").strip()
            if name:
                red[name] += 1
    total = len(drafts)

    def fmt(counter: Counter) -> list[dict]:
        return [
            {"champion": c, "count": n,
             "pct": round(100 * n / total, 1) if total else 0.0}
            for c, n in counter.most_common(top_n)
        ]

    return {"blue": fmt(blue), "red": fmt(red), "total": total}


def first_pick_stats(drafts: list[dict], top_n: int = 10) -> list[dict]:
    """
    Najczęściej first-pickowani championi (pierwszy pick draftu = b1_pick,
    zawsze po stronie Blue — w standardowym draft pickach kolejność to
    B1, R1, R2, B2, B3, R3, ..., więc B1 jest globalnym first pickiem).

    Zwraca listę top_n elementów {champion, count, pct}, gdzie pct to
    udział draftów, w których ten champion był pierwszym pickiem.
    """
    counter: Counter = Counter()
    for d in drafts:
        name = (d.get("b1_pick") or "").strip()
        if name:
            counter[name] += 1
    total = len(drafts)
    return [
        {"champion": c, "count": n,
         "pct": round(100 * n / total, 1) if total else 0.0}
        for c, n in counter.most_common(top_n)
    ]
