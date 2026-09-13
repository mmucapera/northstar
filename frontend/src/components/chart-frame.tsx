import { useState, type ReactNode } from "react";
import { Maximize2 } from "lucide-react";
import { Panel } from "@/components/ui-kit";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

/** Wraps a chart Panel with a maximize button - opens the same chart
 * (re-rendered via the height-taking render prop, so it's one chart
 * definition, not two) full-width in a dialog, for when the compact panel
 * makes month labels or fine detail hard to read. */
export function ChartFrame({
  title,
  note,
  height = 190,
  expandedHeight = 420,
  actions,
  children,
}: {
  title: string;
  note?: string;
  height?: number;
  expandedHeight?: number;
  /** Extra actions (e.g. an export button) shown alongside the maximize button. */
  actions?: ReactNode;
  children: (height: number) => ReactNode;
}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <Panel
        title={title}
        note={note}
        actions={
          <div className="flex items-center gap-1">
            {actions}
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-label={`Maximize ${title}`}
              title="Maximize"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <Maximize2 className="size-4" aria-hidden />
            </button>
          </div>
        }
      >
        {children(height)}
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-4xl">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {note ? <p className="text-xs text-muted-foreground">{note}</p> : null}
          </DialogHeader>
          <div className="mt-2">{children(expandedHeight)}</div>
        </DialogContent>
      </Dialog>
    </>
  );
}
