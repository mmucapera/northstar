// Server-only: checks a login attempt against dbo.AuthorizedUsers in the
// webapp's own Fabric SQL Database (terraform/fabric_sql_database.tf) - not
// the Lakehouse. The lakehouse-backed version of this (Files/users.csv ->
// nb_get_users -> dbo.users, refreshed nightly by pl_auth) meant an edit to
// the allowlist took up to 24h to take effect; a real database has no such
// lag. Login is server-authoritative: the client never sees the full user
// list, only an authorized/not-authorized answer for the one email it
// submitted.

import { createServerFn } from "@tanstack/react-start";
import { connectWebappDb } from "@/data/webapp-db";

async function fetchAuthorizedUsers(): Promise<Map<string, string>> {
  const pool = await connectWebappDb();
  try {
    const result = await pool.request().query("SELECT Email, UserGroup FROM dbo.AuthorizedUsers");
    const map = new Map<string, string>();
    for (const row of result.recordset as { Email: string; UserGroup: string }[]) {
      map.set(row.Email.trim().toLowerCase(), row.UserGroup);
    }
    return map;
  } finally {
    await pool.close();
  }
}

// A real database has no meaningful refresh lag, but caching briefly still
// avoids opening a fresh SQL connection on every single login attempt.
const CACHE_TTL_MS = 60 * 1000;
let cache: { data: Map<string, string>; expiresAt: number } | null = null;
let inFlight: Promise<Map<string, string>> | null = null;

async function fetchAuthorizedUsersCached(): Promise<Map<string, string>> {
  const now = Date.now();
  if (cache && cache.expiresAt > now) return cache.data;
  if (inFlight) return inFlight;
  inFlight = fetchAuthorizedUsers()
    .then((data) => {
      cache = { data, expiresAt: Date.now() + CACHE_TTL_MS };
      return data;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

export type AuthCheckResult = { authorized: true; group: string } | { authorized: false };

export const checkAuthorizedUser = createServerFn({ method: "POST" })
  .validator((data: { email: string }) => data)
  .handler(async ({ data }): Promise<AuthCheckResult> => {
    try {
      const users = await fetchAuthorizedUsersCached();
      const group = users.get(data.email.trim().toLowerCase());
      return group ? { authorized: true, group } : { authorized: false };
    } catch (err) {
      // Fail closed: if the allowlist can't be verified, nobody gets in.
      console.error("[auth-check] failed to check authorized users:", err);
      return { authorized: false };
    }
  });
