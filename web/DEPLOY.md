# Deploy na Vercel

Improve Team Tools = monorepo. Web app żyje w `web/` — Vercel musi
dostać tę ścieżkę jako Root Directory.

## 1. Połączenie z GitHubem

1. https://vercel.com → Login with GitHub.
2. **Add New → Project** → wybierz `dexter2030/Improve_Team_Tools`.
3. **Configure Project**:
   - **Framework Preset**: Next.js (auto-detect po ustawieniu Root Dir).
   - **Root Directory**: `web` ← **kluczowe**, kliknij "Edit" i wpisz.
   - **Build Command**: (zostaw default — `next build`).
   - **Output Directory**: (zostaw default — `.next`).
   - **Install Command**: (zostaw default — `npm install`).
   - **Node.js Version**: 22.x.

## 2. Environment Variables

W tej samej sekcji "Configure" rozwiń **Environment Variables**. Wklej
wszystkie naraz (Vercel ma "Paste .env" — łatwiej). Te są wymagane:

```env
# Supabase pooler (NIE direct connection — Vercel nie ma IPv6 do db.X.supabase.co)
DATABASE_URL=postgresql://postgres.apjjeztgdocravmmxnyd:HASLO@aws-1-eu-central-1.pooler.supabase.com:5432/postgres

# Supabase REST (na razie używane do health check; przyda się Faza+)
NEXT_PUBLIC_SUPABASE_URL=https://apjjeztgdocravmmxnyd.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=sb_publishable_xxx

# Riot API key — dev wygasa co 24h
RIOT_API_KEY=RGAPI-...

# Leaguepedia bot-password (podnosi rate limit z anon ~1req/30s na kilka/s)
LEAGUEPEDIA_USERNAME=Konto@NazwaBota
LEAGUEPEDIA_PASSWORD=...

# Bramka loginowa
APP_PASSWORD=mocne-haslo-do-strony
AUTH_SECRET=losowy-string-min-32-znaki-tylko-dla-produkcji
```

**Ważne:**
- `AUTH_SECRET` musi być **inny** niż lokalny. Wygeneruj np.:
  `openssl rand -base64 48` lub https://generate-secret.vercel.app/32
- `APP_PASSWORD` — to hasło użytkownicy będą wpisywać przy wejściu.
- Klucz Riot na produkcji wygasa co 24h jak dev — odśwież na
  developer.riotgames.com.

## 3. Deploy

Klik **Deploy**. Pierwszy build ~2-3 min:
1. Install deps
2. `next build` (kompilacja Turbopack + SSG dla static pages)
3. Drizzle nie biegnie automatycznie — schema MUSI być już zaaplikowana
   w Supabase (zrobiono lokalnie podczas dev przez `drizzle-kit migrate`).

Po sukcesie dostajesz URL `<projekt>.vercel.app`. Klik → zobaczysz
**login screen** (jeśli APP_PASSWORD ustawiony) → po zalogowaniu cały
dashboard.

## 4. Custom domena (opcjonalnie)

Vercel project → **Settings → Domains** → dodaj domenę (musi być
kupiona oddzielnie, np. Cloudflare Registrar). Vercel pokaże co dodać
w DNS (CNAME `cname.vercel-dns.com` lub A record).

SSL leci auto (Let's Encrypt).

## 5. Po pierwszym deployu

- Dodaj graczy w **Add Player**.
- W **Database** wczytaj ligi z których będziesz analizować drafty.
- W **Players Data** zsynchronizuj globalną bazę (~20k graczy, 20s).
- Następne pushe na `main` → auto-redeploy (~1 min).

## 6. Migracje schema (gdy zmienisz tabele)

```bash
cd web
npx drizzle-kit generate --name <opis>
git add drizzle/
git commit -m "..."
npx drizzle-kit migrate   # od razu aplikuje do prod-bazy Supabase
git push
```

Drizzle migrate odpalasz lokalnie z `.env.local`, który wskazuje na tę
samą Supabase (jeden projekt = jedna baza między dev i prod).

## TODO: Backup do Google Drive

Plan na osobny PR:
1. Service Account w Google Cloud + JSON key.
2. Folder Drive shared z `<sa>@<project>.iam.gserviceaccount.com`.
3. Vercel Cron Job (`app/api/cron/backup/route.ts`) co 24h:
   - Eksportuje `scouting_profiles`, `drafts`, `lp_players_all` jako JSON.
   - Upload do Drive przez `googleapis` package.
4. ENV: `GOOGLE_SERVICE_ACCOUNT_KEY` (cały JSON jako string),
   `BACKUP_DRIVE_FOLDER_ID`.

Bez backup'a obecnie: dane żyją wyłącznie w Supabase. Free tier ma
codzienne backupy ale tylko 7 dni retention.
