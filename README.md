# Improve Team Tools

LoL Scouting Dashboard — Next.js + Supabase + Vercel.

Repo zawiera dwie wersje aplikacji:

- **`web/`** — aktywna, Next.js 16 + TypeScript + Tailwind + Drizzle ORM.
  Production-ready. Deploy: zobacz [`web/DEPLOY.md`](web/DEPLOY.md).
- **`app/` + `src/` + `draft_analyzer/`** — legacy Streamlit MVP (Python).
  Trzymane jako referencja podczas migracji; nowa rozbudowa idzie w `web/`.

## Setup lokalny (web/)

```bash
cd web
npm install
cp .env.local.example .env.local
# uzupełnij DATABASE_URL, RIOT_API_KEY, APP_PASSWORD itp.
npx drizzle-kit migrate    # raz, dla świeżego projektu Supabase
npm run dev                # http://localhost:3000
```

## Zakładki

1. **Scouting List** — lista obserwowanych zawodników z statusem
   weryfikacji (RESOLVED / PARTIAL / FAILED).
2. **Add Player** — formularz dodawania (op.gg + Leaguepedia → live
   weryfikacja przez Riot + Cargo API).
3. **Draft Analyzer** — statystyki pick & ban, top first picks, top
   first-phase bans per side, tabela ostatnich draftów.
4. **Database** — kontrolki synchronizacji Leaguepedia per liga (Tier 1,
   ERL D1, ERL D2 — 27 lig wspieranych).
5. **Players Data** — globalna baza graczy (~20k) z filtrami: rola, kraj,
   retired.
6. **Match Data** — pełny widok pick & ban wszystkich draftów.
7. **Settings** — placeholder dla future config.

## Architektura

```
web/src/
├── app/                 # Next.js App Router
│   ├── (dashboard)/     # route group za auth, z sidebarem
│   ├── api/             # route handlers (health, auth)
│   └── login/
├── components/          # shared UI (sidebar, status badge, champion icon)
└── lib/
    ├── auth/            # HMAC-signed session cookies
    ├── db/              # Drizzle schema + client (Postgres przez Supavisor)
    ├── riot/            # Riot API client (Account-V1, Summoner-V4, League-V4)
    ├── leaguepedia/     # MediaWiki Cargo client + bot-password login
    ├── profiles/        # scouting domain (resolver, repository, links)
    ├── drafts/          # draft sync + analyzer + champion-icons (DDragon)
    └── players/         # global Leaguepedia Players sync
```

## Legacy Streamlit (do referencji)

```
pip install -r requirements.txt
streamlit run app/main.py
```

Streamlit MVP używa SQLite (`scouting.db`, `drafts.db`) lokalnie i tych
samych źródeł danych. Migracja → Next.js trwa, ale Streamlit dalej
działa równolegle dopóki nie zwinie się do `legacy/`.
