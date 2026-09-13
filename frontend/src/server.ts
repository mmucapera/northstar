import "./lib/error-capture";

import { consumeLastCapturedError } from "./lib/error-capture";
import { renderErrorPage } from "./lib/error-page";

type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

let serverEntryPromise: Promise<ServerEntry> | undefined;

async function getServerEntry(): Promise<ServerEntry> {
  if (!serverEntryPromise) {
    serverEntryPromise = import("@tanstack/react-start/server-entry").then(
      (m) => (m.default ?? m) as ServerEntry,
    );
  }
  return serverEntryPromise;
}

// h3 swallows in-handler throws into a normal 500 Response with body
// {"unhandled":true,"message":"HTTPError"} — try/catch alone never fires for those.
async function normalizeCatastrophicSsrResponse(response: Response): Promise<Response> {
  if (response.status < 500) return response;
  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) return response;

  const body = await response.clone().text();
  if (!isH3SwallowedErrorBody(body)) return response;

  console.error(consumeLastCapturedError() ?? new Error(`h3 swallowed SSR error: ${body}`));
  return new Response(renderErrorPage(), {
    status: 500,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

function isH3SwallowedErrorBody(body: string): boolean {
  try {
    const payload = JSON.parse(body) as { unhandled?: unknown; message?: unknown };
    return payload.unhandled === true && payload.message === "HTTPError";
  } catch {
    return false;
  }
}

// Azure App Service terminates TLS at its front-end and forwards plain HTTP
// to this process, setting X-Forwarded-Proto: https. TanStack Start's
// built-in CSRF middleware compares the browser's Origin header against
// `new URL(request.url).origin` - which, left uncorrected, is built from the
// http:// request this process actually receives, so it never matches the
// browser's https:// Origin and every client-invoked server function
// (login, access-log writes, etc.) gets a silent 403. Rewrite the request's
// URL to the externally-visible https:// origin before handing it off.
function withForwardedProtocol(request: Request): Request {
  const forwardedProto = request.headers.get("x-forwarded-proto");
  const url = new URL(request.url);
  if (!forwardedProto || url.protocol === `${forwardedProto}:`) return request;
  url.protocol = `${forwardedProto}:`;
  return new Request(url, {
    method: request.method,
    headers: request.headers,
    body: request.body,
    // @ts-expect-error - required by the fetch spec when body is a stream, not in the DOM lib types
    duplex: request.body ? "half" : undefined,
  });
}

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    try {
      const handler = await getServerEntry();
      const response = await handler.fetch(withForwardedProtocol(request), env, ctx);
      return await normalizeCatastrophicSsrResponse(response);
    } catch (error) {
      console.error(error);
      return new Response(renderErrorPage(), {
        status: 500,
        headers: { "content-type": "text/html; charset=utf-8" },
      });
    }
  },
};
