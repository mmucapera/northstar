import { createFileRoute } from "@tanstack/react-router";
import { useState } from "react";
import {
  BarChart3,
  Check,
  FileSpreadsheet,
  Layers,
  Lock,
  MessagesSquare,
  Send,
  ShieldCheck,
  Target,
  Wand2,
  Workflow,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { PageHeader, Panel } from "@/components/ui-kit";
import { useAuth } from "@/components/auth-context";
import { createTicket } from "@/data/workflow";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export const Route = createFileRoute("/roadmap")({
  head: () => ({
    meta: [
      { title: "Roadmap — Delta Basin" },
      { name: "description", content: "What a Premium package adds on top of the current pilot." },
    ],
  }),
  component: RoadmapPage,
});

type Feature = { icon: LucideIcon; title: string; description: string };

const PLATFORM_FEATURES: Feature[] = [
  {
    icon: Layers,
    title: "Multi-asset rollup",
    description: "Aggregate JV performance across every asset in one view, instead of switching between them.",
  },
  {
    icon: FileSpreadsheet,
    title: "Custom report builder",
    description: "Drag-and-drop report templates, scheduled delivery to stakeholders on your own cadence.",
  },
  {
    icon: ShieldCheck,
    title: "Role-based data exports",
    description: "Governed exports that respect each user's access scope automatically.",
  },
  {
    icon: Target,
    title: "Forecast accuracy",
    description: "Track how close production forecasts land against actuals over time, by field and period.",
  },
];

const SUPPORT_FEATURES: Feature[] = [
  {
    icon: Zap,
    title: "SLA-backed priority routing",
    description: "Guaranteed response times by severity, with automatic escalation if a ticket goes quiet.",
  },
  {
    icon: Wand2,
    title: "AI-suggested resolutions",
    description: "Drafts a response from similar past tickets before a human ever opens it.",
  },
  {
    icon: MessagesSquare,
    title: "Slack / Teams escalation",
    description: "Critical tickets post straight into the right team's channel, two-way synced.",
  },
  {
    icon: Workflow,
    title: "Custom approval workflows",
    description: "Route by department with multi-step sign-off, matching your existing chain of command.",
  },
  {
    icon: BarChart3,
    title: "Resolution analytics",
    description: "Time-to-close, backlog trends and team load, broken down by category and department.",
  },
  {
    icon: Send,
    title: "Direct vendor / regulator escalation",
    description: "HSE tickets above a severity threshold auto-notify the relevant external contact.",
  },
];

function FeatureGrid({
  features,
  requested,
  onRequest,
}: {
  features: Feature[];
  requested: Set<string>;
  onRequest: (feature: Feature) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {features.map((f) => {
        const sent = requested.has(f.title);
        return (
          <div
            key={f.title}
            className="relative flex flex-col gap-2 rounded-md border border-dashed border-border bg-surface/40 p-3"
          >
            <div className="flex items-center justify-between gap-2">
              <f.icon className="size-4 text-muted-foreground" aria-hidden />
              <span className="tabular flex items-center gap-1 rounded-sm border border-primary/40 bg-primary/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-primary">
                <Lock className="size-2.5" aria-hidden />
                Premium
              </span>
            </div>
            <p className="text-sm font-medium text-foreground">{f.title}</p>
            <p className="text-xs leading-relaxed text-muted-foreground">{f.description}</p>
            {sent ? (
              <span className="mt-1 flex w-fit items-center gap-1.5 rounded-md border border-positive/40 bg-positive/10 px-2.5 py-1 text-[11px] uppercase tracking-[0.1em] text-positive">
                <Check className="size-3" aria-hidden />
                Request sent
              </span>
            ) : (
              <button
                type="button"
                onClick={() => onRequest(f)}
                className="mt-1 w-fit rounded-md border border-primary/50 px-2.5 py-1 text-[11px] uppercase tracking-[0.1em] text-primary transition-colors hover:bg-primary/10"
              >
                Upgrade to unlock
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function RoadmapPage() {
  const { user } = useAuth();
  const [pending, setPending] = useState<Feature | null>(null);
  const [requested, setRequested] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  async function confirmRequest() {
    if (!pending || !user) return;
    setSubmitting(true);
    try {
      await createTicket({
        data: {
          subject: `Premium interest: ${pending.title}`,
          description: `Requesting more information on the "${pending.title}" Premium feature and pricing to unlock it.`,
          category: "technical",
          createdByEmail: user.email,
          createdByName: user.name,
        },
      });
      setRequested((prev) => new Set(prev).add(pending.title));
    } finally {
      setSubmitting(false);
      setPending(null);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="Roadmap"
        title="What Premium adds"
        description="A preview of platform and support capabilities on top of what's in this pilot today — none of this is built yet, this is a look at where it's headed."
      />

      <Panel title="Platform" note="Beyond the core reconciliation, production and HSE views">
        <FeatureGrid features={PLATFORM_FEATURES} requested={requested} onRequest={setPending} />
      </Panel>

      <Panel title="Support" note="On top of the ticket queue in Tickets">
        <FeatureGrid features={SUPPORT_FEATURES} requested={requested} onRequest={setPending} />
      </Panel>

      <AlertDialog open={pending !== null} onOpenChange={(open) => !open && setPending(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Request info on "{pending?.title}"?</AlertDialogTitle>
            <AlertDialogDescription>
              This raises a ticket to the technical team building this platform, asking them to reach out with
              pricing and next steps for the Premium package.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction disabled={submitting} onClick={() => void confirmRequest()}>
              {submitting ? "Sending…" : "Send request"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
