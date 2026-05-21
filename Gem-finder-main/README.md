# Gem-finder

Pipeline scoutingowy dla LoL: Leaguepedia → lolpros.gg → Riot API → SQLite.

## Co tu jest

Baza graczy pro/półpro z wybranych lig, ich aktualnych kont soloQ i snapshotów
statystyk pobieranych z Riot API. **Nie ma jeszcze** warstwy Streamlit ani
Hidden Gem Score — tylko pobieranie i baza.

```
scouting/
├── config.py        # ładowanie config.yaml + .env
├── leaguepedia.py   # KROK 1: Cargo API -> lista aktywnych graczy
├── lolpros.py       # KROK 2: scraping lolpros.gg -> Riot accounts
├── soloq.py         # KROK 3: Riot API + rate limiting + match stats
├── database.py      # KROK 4: SQLite (players, snapshots, benchmarks)
└── pipeline.py      # KROK 5: orchestrator (bootstrap / refresh_stale / manual)
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # wpisz RIOT_API_KEY z developer.riotgames.com
```

Edytuj `config.yaml`: ligi, okres aktywności, liczba meczów per gracz.

## Użycie

```bash
# pełny przebieg dla małych lig (test end-to-end)
python -m scouting.pipeline

# z kodu
from datetime import datetime, timedelta
from scouting import bootstrap, refresh_stale, add_manual_player

bootstrap(
    leagues=["LFL", "Ultraliga"],
    active_since=datetime.utcnow() - timedelta(days=180),
)

# cykliczne odświeżanie snapshotów (cron / GitHub Action)
refresh_stale(days=7)

# gracz spoza Leaguepedii
add_manual_player(
    nick="SomeProspect",
    riot_id="Prospect", tag="EUW",
    region="EUW1", role="Mid", league="manual",
)
```

## Rate limiting

- Riot dev-key: 20 req/s + 100 req/120s — globalny limiter w `RiotClient.limiter`
- 429 z `Retry-After` jest honorowane
- lolpros.gg: throttle 1.5s między requestami, sekwencyjnie (konfig)

## Co loguje (`scout.log`)

- każdy gracz nieznaleziony na lolpros (`no-lolpros: <nick>`)
- każdy błąd Riot API (4xx/5xx)
- każda zmiana `riot_id` przypisana do znanego puuid (tabela `riot_id_history`)

## Idempotentność

`bootstrap` używa `puuid` jako klucza głównego — można puścić wielokrotnie,
nie duplikuje graczy. Snapshoty są dopisywane (każde wywołanie = nowy wiersz
w `soloq_snapshots`), żeby trackować zmianę formy w czasie.
