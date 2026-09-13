// Server-only: records webapp access events (logins, logouts, and page
// visits) straight into the webapp's own Fabric SQL Database
// (dbo.WebAccessLog - see terraform/fabric_sql_database.tf), not the
// Lakehouse. The Lakehouse's SQL analytics endpoint is read-only, so the
// only write path into it was a OneLake file drop + a Spark notebook
// ingesting it on a schedule - visible only minutes later. A single INSERT
// against a real database is visible immediately, which is the whole point
// of moving this here.
//
// Geo (country/city/continent) is resolved via a single-IP lookup, fired
// after the INSERT and NOT awaited - the row is already committed and the
// response already on its way back to the browser by the time this runs, so
// a slow or rate-limited geo lookup never blocks a page navigation or
// sign-in. An in-memory per-IP cache avoids repeat external calls for the
// same visitor within this process's lifetime.

import { createServerFn } from "@tanstack/react-start";
import { getRequestHeader, getRequestIP } from "@tanstack/start-server-core";
import { connectWebappDb } from "@/data/webapp-db";

export type AccessEventType = "login" | "logout" | "page_visit";

export type AccessLogEvent = {
  eventType: AccessEventType;
  timestamp: string;
  userEmail: string | null;
  userName: string | null;
  userRole: string | null;
  path: string;
  durationMs: number | null;
  referrer: string | null;
};

const geoCache = new Map<string, { country: string | null; city: string | null; continent: string | null }>();

async function resolveGeo(ip: string) {
  if (geoCache.has(ip)) return geoCache.get(ip)!;
  try {
    const resp = await fetch(`http://ip-api.com/json/${encodeURIComponent(ip)}?fields=status,country,city,continent`);
    const body = (await resp.json()) as { status: string; country?: string; city?: string; continent?: string };
    const geo =
      body.status === "success"
        ? { country: body.country ?? null, city: body.city ?? null, continent: body.continent ?? null }
        : { country: null, city: null, continent: null };
    geoCache.set(ip, geo);
    return geo;
  } catch {
    return { country: null, city: null, continent: null };
  }
}

async function insertEvent(event: AccessLogEvent & { ip: string | null; userAgent: string | null }): Promise<void> {
  const [{ default: sql }] = await Promise.all([import("mssql")]);
  const pool = await connectWebappDb();
  const result = await pool
    .request()
    .input("eventType", sql.NVarChar, event.eventType)
    .input("eventTimestamp", sql.DateTime2, new Date(event.timestamp))
    .input("userEmail", sql.NVarChar, event.userEmail)
    .input("userName", sql.NVarChar, event.userName)
    .input("userRole", sql.NVarChar, event.userRole)
    .input("path", sql.NVarChar, event.path)
    .input("durationMs", sql.BigInt, event.durationMs)
    .input("referrer", sql.NVarChar, event.referrer)
    .input("ip", sql.NVarChar, event.ip)
    .input("userAgent", sql.NVarChar, event.userAgent).query(`
      INSERT INTO dbo.WebAccessLog
        (EventType, EventTimestamp, UserEmail, UserName, UserRole, Path, DurationMs, Referrer, Ip, UserAgent)
      OUTPUT INSERTED.Id
      VALUES
        (@eventType, @eventTimestamp, @userEmail, @userName, @userRole, @path, @durationMs, @referrer, @ip, @userAgent)
    `);
  const id = result.recordset[0]?.Id as number | undefined;

  if (id && event.ip) {
    // Fire-and-forget: resolve geo and backfill the row, without holding up
    // the response this handler is about to return. The pool stays open
    // until this background work finishes (it, not the caller, closes it) -
    // closing it right after the INSERT would cancel the pending UPDATE.
    void resolveGeo(event.ip)
      .then((geo) => {
        if (!geo.country && !geo.city && !geo.continent) return;
        return pool
          .request()
          .input("id", sql.BigInt, id)
          .input("country", sql.NVarChar, geo.country)
          .input("city", sql.NVarChar, geo.city)
          .input("continent", sql.NVarChar, geo.continent)
          .query("UPDATE dbo.WebAccessLog SET Country = @country, City = @city, Continent = @continent WHERE Id = @id");
      })
      .catch(() => {
        /* best-effort geo enrichment - never surfaces to the caller */
      })
      .finally(() => {
        pool.close().catch(() => {});
      });
  } else {
    await pool.close();
  }
}

// getRequestIP can return "host:port" (observed behind Azure's proxy, e.g.
// "178.51.4.80:9255") rather than a bare address - strip the port so the
// stored IP and the geo lookup both get a clean address. IPv6 uses
// "[addr]:port" - strip that shape too rather than mis-splitting on ':'.
function cleanIp(raw: string): string {
  const bracketed = raw.match(/^\[(.+)]:\d+$/);
  if (bracketed) return bracketed[1]!;
  if (raw.includes(":") && !raw.includes("::") && raw.split(":").length === 2) {
    return raw.split(":")[0]!;
  }
  return raw;
}

export const logAccessEvent = createServerFn({ method: "POST" })
  .validator((data: AccessLogEvent) => data)
  .handler(async ({ data }) => {
    try {
      const rawIp = getRequestIP({ xForwardedFor: true });
      const ip = rawIp ? cleanIp(rawIp) : null;
      const userAgent = getRequestHeader("user-agent") ?? null;
      await insertEvent({ ...data, ip, userAgent });
    } catch (err) {
      // Never let logging failures break the page - just note it server-side.
      console.error("[access-log] failed to write event:", err);
    }
    return null;
  });
