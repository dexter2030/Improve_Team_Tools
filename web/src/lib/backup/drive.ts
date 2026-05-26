/**
 * Google Drive — upload + rotacja przez REST (lekki bundle).
 *
 * Service Account → JWT (RS256) → access_token → REST API. Pełny
 * `googleapis` SDK to ~3-4 MB w bundle; tu używamy tylko
 * `google-auth-library` (~500 KB) do podpisu JWT i ręcznie multipart
 * upload do Drive API. Mniejszy cold start serverless.
 *
 * Scope `drive.file` (zamiast pełnego `drive`) ogranicza dostęp tylko
 * do plików stworzonych przez tę aplikację — bezpieczniej.
 */

import "server-only";

import { JWT } from "google-auth-library";

interface ServiceAccountKey {
  client_email: string;
  private_key: string;
}

function getServiceAccountKey(): ServiceAccountKey {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_KEY;
  if (!raw) {
    throw new Error("GOOGLE_SERVICE_ACCOUNT_KEY env var is not set");
  }
  const parsed = JSON.parse(raw) as Partial<ServiceAccountKey>;
  if (!parsed.client_email || !parsed.private_key) {
    throw new Error(
      "GOOGLE_SERVICE_ACCOUNT_KEY missing client_email or private_key"
    );
  }
  return { client_email: parsed.client_email, private_key: parsed.private_key };
}

async function getAccessToken(): Promise<string> {
  const key = getServiceAccountKey();
  const client = new JWT({
    email: key.client_email,
    key: key.private_key,
    scopes: ["https://www.googleapis.com/auth/drive.file"],
  });
  const { token } = await client.getAccessToken();
  if (!token) {
    throw new Error("Failed to obtain Google access token");
  }
  return token;
}

export interface UploadedFile {
  id: string;
  name: string;
}

/** Multipart upload pojedynczego pliku JSON do wskazanego folderu. */
export async function uploadJson(
  filename: string,
  content: string,
  folderId: string
): Promise<UploadedFile> {
  const token = await getAccessToken();
  const boundary = `itt_${Date.now().toString(36)}_${Math.random()
    .toString(36)
    .slice(2)}`;
  const metadata = JSON.stringify({ name: filename, parents: [folderId] });
  const body =
    `--${boundary}\r\n` +
    `Content-Type: application/json; charset=UTF-8\r\n\r\n` +
    `${metadata}\r\n` +
    `--${boundary}\r\n` +
    `Content-Type: application/json\r\n\r\n` +
    `${content}\r\n` +
    `--${boundary}--`;

  const res = await fetch(
    "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart&supportsAllDrives=true",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": `multipart/related; boundary=${boundary}`,
      },
      body,
    }
  );
  if (!res.ok) {
    throw new Error(
      `Drive upload failed: ${res.status} ${res.statusText} — ${await res.text()}`
    );
  }
  return (await res.json()) as UploadedFile;
}

export interface RotationResult {
  kept: number;
  deleted: number;
}

/**
 * Trzyma `keepLast` najnowszych plików o nazwie zaczynającej się od
 * `namePrefix` w folderze; starsze usuwa. Zwraca licznik dla telemetrii.
 *
 * Sortowanie po `createdTime` (nie `name`) — odporne na zmianę formatu
 * nazwy pliku w przyszłości.
 */
export async function rotate(
  folderId: string,
  keepLast: number,
  namePrefix: string
): Promise<RotationResult> {
  const token = await getAccessToken();
  const q = `'${folderId}' in parents and name contains '${namePrefix}' and trashed = false`;
  const url =
    `https://www.googleapis.com/drive/v3/files?` +
    new URLSearchParams({
      q,
      orderBy: "createdTime desc",
      fields: "files(id,name,createdTime)",
      pageSize: "1000",
      supportsAllDrives: "true",
      includeItemsFromAllDrives: "true",
    }).toString();

  const listRes = await fetch(url, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!listRes.ok) {
    throw new Error(
      `Drive list failed: ${listRes.status} ${listRes.statusText} — ${await listRes.text()}`
    );
  }
  const data = (await listRes.json()) as {
    files: { id: string; name: string }[];
  };

  const toDelete = data.files.slice(keepLast);
  for (const file of toDelete) {
    const delRes = await fetch(
      `https://www.googleapis.com/drive/v3/files/${file.id}?supportsAllDrives=true`,
      {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
      }
    );
    if (!delRes.ok && delRes.status !== 404) {
      throw new Error(
        `Drive delete failed for ${file.name}: ${delRes.status} ${delRes.statusText}`
      );
    }
  }

  return {
    kept: Math.min(data.files.length, keepLast),
    deleted: toDelete.length,
  };
}
