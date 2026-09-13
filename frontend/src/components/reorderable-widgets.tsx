import { useEffect, useState, type ReactNode } from "react";
import {
  DndContext,
  closestCenter,
  PointerSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
  type DragOverEvent,
  type DragStartEvent,
} from "@dnd-kit/core";
import { SortableContext, verticalListSortingStrategy, useSortable, arrayMove } from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import { Check, GripVertical, LayoutGrid, RotateCcw } from "lucide-react";
import { useAuth } from "@/components/auth-context";
import { getDashboardLayout, setDashboardLayout, resetDashboardLayout } from "@/data/workflow";

export type DashboardWidget = { id: string; content: ReactNode };

function SortableWidget({
  id,
  editing,
  jiggleDelay,
  dropIndicator,
  children,
}: {
  id: string;
  editing: boolean;
  jiggleDelay: number;
  /** Which edge to show the "it'll land here" bar on, or null if this
   * widget isn't the current drop target. */
  dropIndicator: "before" | "after" | null;
  children: ReactNode;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id,
    disabled: !editing,
  });
  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    animationDelay: editing ? `${jiggleDelay}ms` : undefined,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`relative rounded-lg ${editing && !isDragging ? "animate-widget-jiggle ring-1 ring-primary/30" : ""} ${
        isDragging ? "z-20 opacity-90 ring-2 ring-primary/60" : ""
      }`}
    >
      {dropIndicator === "before" ? (
        <div className="absolute -top-2.5 right-0 left-0 z-30 h-1 rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]" />
      ) : null}
      {dropIndicator === "after" ? (
        <div className="absolute -bottom-2.5 right-0 left-0 z-30 h-1 rounded-full bg-primary shadow-[0_0_8px_var(--color-primary)]" />
      ) : null}
      {editing ? (
        <button
          type="button"
          {...attributes}
          {...listeners}
          aria-label="Drag to reorder"
          className="absolute -left-2 -top-2 z-30 flex size-6 cursor-grab items-center justify-center rounded-full border border-border bg-surface-2 text-muted-foreground shadow-sm active:cursor-grabbing"
        >
          <GripVertical className="size-3.5" aria-hidden />
        </button>
      ) : null}
      <div
        className={`rounded-lg transition-shadow ${
          dropIndicator ? "outline outline-2 outline-offset-2 outline-primary/40" : ""
        } ${editing ? "pointer-events-none select-none" : ""}`}
      >
        {children}
      </div>
    </div>
  );
}

/** iOS-home-screen-style widget reordering: a "Customize layout" button
 * enters edit mode (widgets jiggle, drag handles appear, taps are
 * suppressed), drag to reorder, "Done" saves per-user to
 * dbo.UserDashboardLayout keyed on (email, page). Falls back to the
 * caller's default order for first-time users or if the load fails. */
export function ReorderableWidgets({ page, widgets }: { page: string; widgets: DashboardWidget[] }) {
  const { user } = useAuth();
  const defaultOrder = widgets.map((w) => w.id);
  const [order, setOrder] = useState<string[]>(defaultOrder);
  const [editing, setEditing] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const sensors = useSensors(useSensor(PointerSensor, { activationConstraint: { distance: 6 } }));

  useEffect(() => {
    if (!user) return;
    let cancelled = false;
    getDashboardLayout({ data: { email: user.email, page } })
      .then((saved) => {
        if (cancelled || !saved) return;
        // Reconcile with the current widget set: keep saved order for ids
        // that still exist, append any new widgets (e.g. a feature shipped
        // after the user last customized) at the end, drop stale ids.
        const knownIds = new Set(defaultOrder);
        const reconciled = saved.filter((id) => knownIds.has(id));
        for (const id of defaultOrder) if (!reconciled.includes(id)) reconciled.push(id);
        setOrder(reconciled);
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email, page]);

  function onDragStart(e: DragStartEvent) {
    setActiveId(String(e.active.id));
  }

  function onDragOver(e: DragOverEvent) {
    setOverId(e.over ? String(e.over.id) : null);
  }

  function onDragEnd(e: DragEndEvent) {
    const { active, over } = e;
    setActiveId(null);
    setOverId(null);
    if (!over || active.id === over.id) return;
    setOrder((prev) => {
      const oldIndex = prev.indexOf(String(active.id));
      const newIndex = prev.indexOf(String(over.id));
      if (oldIndex === -1 || newIndex === -1) return prev;
      return arrayMove(prev, oldIndex, newIndex);
    });
  }

  async function done() {
    setEditing(false);
    if (!user) return;
    await setDashboardLayout({ data: { email: user.email, page, order } }).catch(() => {});
  }

  async function restoreDefault() {
    setOrder(defaultOrder);
    if (!user) return;
    await resetDashboardLayout({ data: { email: user.email, page } }).catch(() => {});
  }

  const byId = new Map(widgets.map((w) => [w.id, w]));
  const ordered = order.map((id) => byId.get(id)).filter((w): w is DashboardWidget => Boolean(w));

  const activeIndex = activeId ? order.indexOf(activeId) : -1;
  const overIndex = overId ? order.indexOf(overId) : -1;
  const insertAfter = activeIndex !== -1 && overIndex !== -1 && activeIndex < overIndex;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-end gap-2">
        {editing ? (
          <>
            <button
              type="button"
              onClick={() => void restoreDefault()}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
            >
              <RotateCcw className="size-3.5" aria-hidden />
              Restore default layout
            </button>
            <button
              type="button"
              onClick={() => void done()}
              className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground transition-colors hover:bg-primary/90"
            >
              <Check className="size-3.5" aria-hidden />
              Done
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={() => setEditing(true)}
            disabled={!loaded}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
          >
            <LayoutGrid className="size-3.5" aria-hidden />
            Customize layout
          </button>
        )}
      </div>

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragStart={onDragStart}
        onDragOver={onDragOver}
        onDragEnd={onDragEnd}
      >
        <SortableContext items={order} strategy={verticalListSortingStrategy}>
          <div className="space-y-4">
            {ordered.map((w, i) => (
              <SortableWidget
                key={w.id}
                id={w.id}
                editing={editing}
                jiggleDelay={(i % 4) * 60}
                dropIndicator={overId === w.id && w.id !== activeId ? (insertAfter ? "after" : "before") : null}
              >
                {w.content}
              </SortableWidget>
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </div>
  );
}
