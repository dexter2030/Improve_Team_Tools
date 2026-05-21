# LoL Scouting Dashboard

## Run
    pip install -r requirements.txt
    # create a .env file at the project root with your Riot API key:
    #   RIOT_API_KEY=RGAPI-...
    streamlit run app/main.py

## Tabs
- **Scouting List / Add Player** — track prospects, resolve identities.
- **Draft Analyzer** — historical pick & ban analysis (`draft_analyzer/`).
  Has its own SQLite store (`draft_analyzer/drafts.db`); load data from
  Leaguepedia inside the tab before analyzing.

## Notes
- Players persist in `scouting.db` (SQLite, auto-created on first run).
  The same file holds the Riot / Leaguepedia API response cache.
- Identities resolve live: Riot API for SoloQ, Leaguepedia for pro play.
- A Riot development API key expires every 24h — refresh `RIOT_API_KEY`
  in `.env` when calls start returning 401/403.
