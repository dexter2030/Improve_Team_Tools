"""
shared — kod współdzielony przez aplikacje Pythona w monorepo.

Zawiera tylko warstwę, która jest naprawdę wspólna dla wielu aplikacji:

- ``shared.api``        — klienci źródeł danych (Leaguepedia/Cargo, Riot API)
                          oraz prymitywy cache (``SqliteCacheStore`` + ``CacheStore``).
- ``shared.lolpros``    — scraper kont z lolpros.gg.
- ``shared.processing`` — czysta logika domenowa niezależna od aplikacji
                          (``match_stats``).

Aplikacje (``apps/streamlit-dashboard``, ``apps/gem-finder``) dokładają
``packages/shared`` do ``sys.path`` małym bootstrapem i importują ``shared.*``.
Pakiet nie ma żadnej zależności zwrotnej do kodu konkretnej aplikacji.
"""
