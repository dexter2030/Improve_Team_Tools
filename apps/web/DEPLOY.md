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

# Riot API key — Personal (App ID 838521, NIE wygasa co 24h).
# Można zregenerować w developer.riotgames.com (Personal API Key → Regenerate).
RIOT_API_KEY=RGAPI-...

# Leaguepedia bot-password (podnosi rate limit z anon ~1req/30s na kilka/s)
LEAGUEPEDIA_USERNAME=Konto@NazwaBota
LEAGUEPEDIA_PASSWORD=...

# Bramka loginowa
APP_PASSWORD=mocne-haslo-do-strony
AUTH_SECRET=losowy-string-min-32-znaki-tylko-dla-produkcji

# Backup do Drive (sekcja 7). Vercel ustawia CRON_SECRET sam — nie wpisuj.
GOOGLE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"...","private_key":"-----BEGIN PRIVATE KEY-----\n..."}
BACKUP_DRIVE_FOLDER_ID=1AbCdEf...
# Opcjonalnie — domyślnie 30 dni retencji.
# BACKUP_RETENTION_DAYS=30
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

## 7. Backup do Google Drive

Cron `0 3 * * *` UTC (4:00 / 5:00 CET zima/lato) leci codziennie i
wrzuca pełen dump bazy jako JSON do shared folderu Drive. Konfiguracja
w `web/vercel.json`, handler w `web/src/app/api/cron/backup/route.ts`.

### TODO — manual setup (jednorazowo, do zrobienia ręcznie)

Kod gotowy, ale dopóki nie wykonasz poniższych kroków, cron będzie
zwracać 500 (brak ENV). Wymagają Twojego konta Google + Vercel, więc
muszą być zrobione ręcznie:

- [ ] §7.1 — Service Account w GCP + pobranie JSON keya
- [ ] §7.2 — Folder na Drive + share z emailem SA jako Editor
- [ ] §7.3 — `GOOGLE_SERVICE_ACCOUNT_KEY` + `BACKUP_DRIVE_FOLDER_ID` w Vercel ENV
- [ ] §7.5 — Test ręczny przez curl, sprawdzenie pliku w folderze
- [ ] Po pierwszym udanym cronie (3:00 UTC dnia po deploy) — odznaczyć tutaj

### 7.1. Service Account

1. https://console.cloud.google.com → **APIs & Services → Library** →
   włącz **Google Drive API**.
2. **IAM & Admin → Service Accounts → Create Service Account**.
   Nazwij np. `itt-backup`. Role może być pusta — uprawnienia daje
   share na folderze (poniżej).
3. W liście SA klik na utworzone konto → **Keys → Add Key → JSON**.
   Pobiera się plik JSON — to całe ENV `GOOGLE_SERVICE_ACCOUNT_KEY`.

### 7.2. Folder Drive

1. https://drive.google.com → New → Folder, np. "Improve Team Tools backups".
2. Right-click → **Share** → wpisz email SA z JSON-a
   (`<nazwa>@<project>.iam.gserviceaccount.com`), nadaj **Editor**.
3. W URL folderu (`https://drive.google.com/drive/folders/XYZ`) skopiuj
   `XYZ` — to `BACKUP_DRIVE_FOLDER_ID`.

### 7.3. Vercel ENV

W Project Settings → Environment Variables dodaj:

```env
GOOGLE_SERVICE_ACCOUNT_KEY={"type":"service_account",...}   # cały JSON jednym stringiem
BACKUP_DRIVE_FOLDER_ID=XYZ
# Opcjonalnie:
# BACKUP_RETENTION_DAYS=30
```

`CRON_SECRET` ustawia się **automatycznie** przy włączeniu cron jobs —
nie wpisuj ręcznie.

### 7.4. Co jest w backupie

Plik `improve-team-tools-backup-<ISO-timestamp>.json` zawiera wszystkie
tabele user-authored + Leaguepedia data (`scouting_profiles`,
`soloq_accounts`, `proplay_identities`, `drafts`, `lp_players_all`,
`lp_tournament_players` + sync-metadata). `api_cache` pominięty —
TTL-based, regeneruje się.

Stare pliki kasowane: trzymamy najnowsze N (default 30), gdzie N
można pokręcić przez `BACKUP_RETENTION_DAYS`.

### 7.5. Test ręczny

Po deploy:

```bash
curl -H "Authorization: Bearer $CRON_SECRET" \
  https://<projekt>.vercel.app/api/cron/backup
```

Odpowiedź zwraca rozmiar i row counts per tabela. Bez Bearera leci 401.
