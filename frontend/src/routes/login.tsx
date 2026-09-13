import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { Building2 } from "lucide-react";
import { useAuth } from "@/components/auth-context";
import { useActivityLog } from "@/components/activity-log-context";
import { resolveAuthorizedUser } from "@/data/auth";
import { checkAuthorizedUser } from "@/data/auth-check";
import { logAccessEvent } from "@/data/access-log";

export const Route = createFileRoute("/login")({
  head: () => ({
    meta: [
      { title: "Sign in — Delta Basin" },
      { name: "robots", content: "noindex" },
    ],
  }),
  component: LoginPage,
});

function LoginPage() {
  const { login } = useAuth();
  const { record } = useActivityLog();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function completeLogin(rawEmail: string) {
    const email = rawEmail.trim().toLowerCase();
    if (!email) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = await checkAuthorizedUser({ data: { email } });
      if (!result.authorized) {
        setError("This email isn't authorized for this pilot.");
        return;
      }
      const user = resolveAuthorizedUser(email, result.group);
      login(user);
      // record() reads the signed-in user from context, so it only fires
      // reliably once `user` is set - queue it just after login() commits.
      queueMicrotask(() => record("auth.login", `${user.name} (${user.role}) signed in.`));
      logAccessEvent({
        data: {
          eventType: "login",
          timestamp: new Date().toISOString(),
          userEmail: user.email,
          userName: user.name,
          userRole: user.role,
          path: "/login",
          durationMs: null,
          referrer: typeof document !== "undefined" ? document.referrer || null : null,
        },
      }).catch(() => {
        /* best-effort - never block sign-in on a logging failure */
      });
      navigate({ to: "/" });
    } catch {
      setError("Sign-in failed — please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void completeLogin(email);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm">
        <div className="text-center">
          {/* Typographic wordmark - no real CUSTOMER0 logo asset is available, so
              this mirrors the reference screenshot's bold-wordmark style
              using the app's own brand color instead of a fabricated logo. */}
          <p className="font-display text-4xl font-bold tracking-tight text-primary">CUSTOMER0</p>
          <h1 className="mt-6 text-xl font-semibold text-foreground">
            Welcome to CUSTOMER0&apos;s Delta&nbsp;Basin
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">Login to get started!</p>
        </div>

        <form onSubmit={onSubmit} className="mt-8 space-y-3">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email address*"
            aria-label="Email address"
            className="w-full rounded-md border border-border bg-surface px-4 py-3 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
          />
          {error ? <p className="text-xs text-critical">{error}</p> : null}
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-3 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Checking…" : "Continue"}
          </button>
        </form>

        <div className="my-5 flex items-center gap-3">
          <span className="h-px flex-1 bg-border" />
          <span className="text-[11px] uppercase tracking-[0.14em] text-muted-foreground">Or</span>
          <span className="h-px flex-1 bg-border" />
        </div>

        <button
          type="button"
          disabled
          title="Not available in this demo pilot - no real CUSTOMER0 EntraID tenant is connected."
          className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-md border border-border bg-surface px-4 py-3 text-sm font-medium text-foreground opacity-60"
        >
          <Building2 className="size-4" aria-hidden />
          Continue with CUSTOMER0 EntraID
        </button>

        <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground">
          Demo pilot — pre-discovery, synthetic data only. No real CUSTOMER0 identity system is
          connected; access is restricted to authorized reviewers.
        </p>
      </div>
    </div>
  );
}
