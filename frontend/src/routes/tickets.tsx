import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { Plus, Rocket } from "lucide-react";
import { PageHeader, Panel, EmptyState, StatusPill, NewBadge } from "@/components/ui-kit";
import { useAuth } from "@/components/auth-context";
import {
  createTicket,
  listTickets,
  updateTicketStatus,
  type Ticket,
  type TicketCategory,
  type TicketStatus,
} from "@/data/workflow";

export const Route = createFileRoute("/tickets")({
  head: () => ({
    meta: [
      { title: "Tickets — Delta Basin" },
      { name: "description", content: "Raise a request to the technical team or a department, and track it through resolution." },
    ],
  }),
  component: TicketsPage,
});

const categoryLabel: Record<TicketCategory, string> = {
  technical: "Technical team",
  finance: "Finance",
  ops: "Operations",
  hse: "HSE",
};

function timestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });
}

function NewTicketForm({ onCreated }: { onCreated: (t: Ticket) => void }) {
  const { user } = useAuth();
  const [subject, setSubject] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState<TicketCategory>("technical");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit() {
    if (!user || !subject.trim() || !description.trim() || submitting) return;
    setSubmitting(true);
    try {
      await createTicket({
        data: {
          subject: subject.trim(),
          description: description.trim(),
          category,
          createdByEmail: user.email,
          createdByName: user.name,
        },
      });
      onCreated({
        id: Date.now(),
        subject: subject.trim(),
        description: description.trim(),
        category,
        status: "open",
        createdByEmail: user.email,
        createdByName: user.name,
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      });
      setSubject("");
      setDescription("");
      setCategory("technical");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-[1fr_auto]">
        <input
          type="text"
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          placeholder="Subject"
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
        />
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as TicketCategory)}
          className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-primary"
        >
          {(Object.keys(categoryLabel) as TicketCategory[]).map((c) => (
            <option key={c} value={c}>
              {categoryLabel[c]}
            </option>
          ))}
        </select>
      </div>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Describe the issue or request…"
        rows={3}
        className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
      />
      <button
        type="button"
        onClick={() => void onSubmit()}
        disabled={submitting || !subject.trim() || !description.trim()}
        className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        <Plus className="size-4" aria-hidden />
        {submitting ? "Submitting…" : "Raise ticket"}
      </button>
    </div>
  );
}

function TicketsPage() {
  const [tickets, setTickets] = useState<Ticket[] | null>(null);
  const [filter, setFilter] = useState<TicketStatus | "all">("all");

  useEffect(() => {
    listTickets()
      .then(setTickets)
      .catch(() => setTickets([]));
  }, []);

  async function changeStatus(id: number, status: TicketStatus) {
    setTickets((prev) => prev?.map((t) => (t.id === id ? { ...t, status } : t)) ?? prev);
    await updateTicketStatus({ data: { id, status } }).catch(() => {});
  }

  const visible = (tickets ?? []).filter((t) => filter === "all" || t.status === filter);

  return (
    <>
      <PageHeader
        eyebrow="Support"
        title="Tickets"
        description="Raise a request to the technical team building this platform, or to a department (Finance, Operations, HSE)."
        actions={<NewBadge />}
      />

      <Panel title="Raise a new ticket">
        <NewTicketForm onCreated={(t) => setTickets((prev) => [t, ...(prev ?? [])])} />
      </Panel>

      <Panel
        title="Ticket queue"
        note={`${visible.length} shown`}
        actions={
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value as TicketStatus | "all")}
            className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-foreground outline-none focus:border-primary"
          >
            <option value="all">All statuses</option>
            <option value="open">Open</option>
            <option value="in_progress">In progress</option>
            <option value="closed">Closed</option>
          </select>
        }
      >
        {tickets === null ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : visible.length === 0 ? (
          <EmptyState title="No tickets yet." hint="Raised tickets will show up here." />
        ) : (
          <div className="space-y-3">
            {visible.map((t) => (
              <div key={t.id} className="rounded-md border border-border bg-surface/60 p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-foreground">{t.subject}</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      {categoryLabel[t.category]} · {t.createdByName ?? t.createdByEmail} · {timestamp(t.createdAt)} UTC
                    </p>
                  </div>
                  <StatusPill status={t.status === "in_progress" ? "watch" : t.status === "closed" ? "settled" : "pending"} />
                </div>
                <p className="mt-2 text-xs leading-relaxed text-foreground">{t.description}</p>
                {t.status !== "closed" ? (
                  <div className="mt-3 flex gap-2">
                    {t.status === "open" ? (
                      <button
                        type="button"
                        onClick={() => void changeStatus(t.id, "in_progress")}
                        className="rounded-md border border-border px-2.5 py-1 text-[11px] uppercase tracking-[0.1em] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
                      >
                        Mark in progress
                      </button>
                    ) : null}
                    <button
                      type="button"
                      onClick={() => void changeStatus(t.id, "closed")}
                      className="rounded-md border border-border px-2.5 py-1 text-[11px] uppercase tracking-[0.1em] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
                    >
                      Close
                    </button>
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Link
        to="/roadmap"
        className="flex items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm transition-colors hover:bg-primary/10"
      >
        <span className="flex items-center gap-2 text-foreground">
          <Rocket className="size-4 text-primary" aria-hidden />
          See what a Premium package adds on top of this ticket queue
        </span>
        <span className="tabular text-xs uppercase tracking-[0.1em] text-primary">Open roadmap →</span>
      </Link>
    </>
  );
}
