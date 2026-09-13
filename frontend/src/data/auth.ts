// Identity directory. Login is now gated server-side against dbo.users (the
// lakehouse-backed allowlist synced from Files/users.csv - see auth-check.ts
// and login.tsx) - only emails in that table can sign in. This module just
// resolves an authorized email + its user_group into a display identity and
// a PersonaId for view-scoping.
//
// Group -> persona mapping is intentionally coarse for now: "ALL" gets the
// broadest existing view (executive). Per-group permissions (which persona
// each user_group should map to, and eventually which report/dashboard
// sections) are explicitly deferred - "later we will define what each user
// group has access to" - so anything not recognized also falls back to
// executive rather than guessing at a narrower scope.

import type { PersonaId } from "@/components/view-context";

export type DemoUser = {
  email: string;
  name: string;
  role: PersonaId;
};

const KNOWN_PERSONA_IDS: PersonaId[] = ["executive", "finance", "ops", "hse"];

function nameFromEmail(email: string): string {
  const local = email.split("@")[0] ?? email;
  return local
    .split(/[._-]+/)
    .filter(Boolean)
    .map((part) => part[0]!.toUpperCase() + part.slice(1))
    .join(" ");
}

/** Builds the signed-in identity for an email dbo.users has already
 * confirmed is authorized. `group` is that row's user_group column. */
export function resolveAuthorizedUser(rawEmail: string, group: string): DemoUser {
  const email = rawEmail.trim().toLowerCase();
  const normalizedGroup = group.trim().toLowerCase();
  const role =
    KNOWN_PERSONA_IDS.find((p) => p === normalizedGroup) ?? "executive";
  return { email, name: nameFromEmail(email) || email, role };
}

/** Simulated SSO identity - "Continue with CUSTOMER0 EntraID" has no real IdP to
 * redirect to, so it signs in as this fixed identity instead. Still goes
 * through the same server-side allowlist check as a typed email. */
export const SSO_DEMO_EMAIL = "mucapera@gmail.com";

/** Audit-log visibility hierarchy: which roles' activity a given role can see,
 * in addition to their own (every role always includes itself). Distinct
 * from PersonaSlice in view-context.tsx, which controls dashboard section
 * visibility, not log visibility. */
export const LOG_VISIBILITY: Record<PersonaId, PersonaId[]> = {
  executive: ["executive", "finance", "ops", "hse"],
  finance: ["finance", "ops", "hse"],
  ops: ["ops", "hse"],
  hse: ["hse"],
};
