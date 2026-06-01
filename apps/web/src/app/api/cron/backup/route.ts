/**
 * GET /api/cron/backup
 *
 * Daily backup → Google Drive. Wzywany przez Vercel Cron (`vercel.json`)
 * raz na dobę z `Authorization: Bearer ${CRON_SECRET}`.
 *
 * Eksportuje wszystkie tabele user-authored + Leaguepedia data jako
 * jeden plik JSON, uploaduje do shared folderu na Drive, usuwa starsze
 * niż `BACKUP_RETENTION_DAYS` (default 30). Snapshot pomija `api_cache`
 * (TTL-based, regeneruje się).
 *
 * Env:
 *   CRON_SECRET                 — auto-set przez Vercel; lokalnie ręcznie.
 *   GOOGLE_SERVICE_ACCOUNT_KEY  — pełny JSON service-account key string.
 *   BACKUP_DRIVE_FOLDER_ID      — ID folderu Drive shared z SA.
 *   BACKUP_RETENTION_DAYS       — opcjonalny override (default 30).
 */

import "server-only";

import type { NextRequest } from "next/server";

import { uploadJson, rotate } from "@/lib/backup/drive";
import { buildSnapshot } from "@/lib/backup/snapshot";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
// Snapshot + multipart upload do Drive — bezpieczny budżet dla ~25 MB JSON.
export const maxDuration = 60;

const FILENAME_PREFIX = "improve-team-tools-backup-";
const DEFAULT_RETENTION = 30;

export async function GET(req: NextRequest) {
  const cronSecret = process.env.CRON_SECRET;
  if (!cronSecret) {
    return Response.json(
      { ok: false, error: "CRON_SECRET env var is not set" },
      { status: 500 }
    );
  }
  if (req.headers.get("authorization") !== `Bearer ${cronSecret}`) {
    return Response.json({ ok: false, error: "unauthorized" }, { status: 401 });
  }

  const folderId = process.env.BACKUP_DRIVE_FOLDER_ID;
  if (!folderId) {
    return Response.json(
      { ok: false, error: "BACKUP_DRIVE_FOLDER_ID env var is not set" },
      { status: 500 }
    );
  }

  const retention = parseRetention(process.env.BACKUP_RETENTION_DAYS);

  try {
    const startedAt = Date.now();
    const snapshot = await buildSnapshot();
    const payload = JSON.stringify(snapshot);
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const filename = `${FILENAME_PREFIX}${timestamp}.json`;

    const uploaded = await uploadJson(filename, payload, folderId);
    const rotation = await rotate(folderId, retention, FILENAME_PREFIX);

    const rows = Object.fromEntries(
      Object.entries(snapshot.tables).map(([table, list]) => [
        table,
        Array.isArray(list) ? list.length : 0,
      ])
    );

    return Response.json({
      ok: true,
      uploaded: { id: uploaded.id, name: uploaded.name },
      rotation,
      rows,
      bytes: payload.length,
      durationMs: Date.now() - startedAt,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return Response.json({ ok: false, error: message }, { status: 500 });
  }
}

function parseRetention(raw: string | undefined): number {
  if (!raw) return DEFAULT_RETENTION;
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return DEFAULT_RETENTION;
  return Math.floor(n);
}
