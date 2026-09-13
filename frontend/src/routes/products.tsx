import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useRef, useState } from "react";
import { ImagePlus, PackageSearch, Pencil, RotateCcw, Trash2 } from "lucide-react";
import { ProductPhoto } from "@/components/product-photo";
import { fileToThumbnailDataUrl } from "@/lib/image-resize";
import { useCatalog } from "@/components/catalog-context";
import {
  ColumnMenu,
  DataTable,
  EmptyState,
  ExportCsvButton,
  Metric,
  PageHeader,
  Panel,
  PrintButton,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import { categories, categoryById, formatUsd, stockStatus, type Product } from "@/data/catalog";
import { formatNumber } from "@/data/delta-basin";

export const Route = createFileRoute("/products")({
  head: () => ({
    meta: [
      { title: "Materials catalogue — Delta Basin stock, prices and SKUs" },
      {
        name: "description",
        content:
          "Browse and edit the Delta Basin materials catalogue: categories, SKUs, unit prices, stock on hand and reorder points.",
      },
      { property: "og:title", content: "Delta Basin materials catalogue" },
      {
        property: "og:description",
        content: "Categories, SKUs, prices and stock levels for the Delta Basin pilot, editable in place.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ProductsPage,
});

type StatusFilter = "all" | "in-stock" | "low-stock" | "out-of-stock";

const statusFilterLabel: Record<StatusFilter, string> = {
  all: "All statuses",
  "in-stock": "In stock",
  "low-stock": "Low stock",
  "out-of-stock": "Out of stock",
};

function ProductsPage() {
  const { items, updateProduct, resetCatalog } = useCatalog();
  const [categoryId, setCategoryId] = useState("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Product | null>(null);

  function toggleStatusFilter(next: StatusFilter) {
    setStatusFilter((prev) => (prev === next ? "all" : next));
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(
      (p) =>
        (categoryId === "all" || p.categoryId === categoryId) &&
        (statusFilter === "all" || stockStatus(p) === statusFilter) &&
        (q === "" || p.name.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)),
    );
  }, [items, categoryId, statusFilter, query]);

  type ProductSortKey = "name" | "category" | "unitPrice" | "stock" | "reorder" | "value" | "status";
  const [sort, setSort] = useState<{ key: ProductSortKey; dir: "asc" | "desc" } | null>(null);

  const sorted = useMemo(() => {
    if (!sort) return filtered;
    const dir = sort.dir === "asc" ? 1 : -1;
    const valueOf = (p: Product): string | number => {
      switch (sort.key) {
        case "name":
          return p.name;
        case "category":
          return categoryById(p.categoryId)?.name ?? p.categoryId;
        case "unitPrice":
          return p.unitPriceUsd;
        case "stock":
          return p.stockQty;
        case "reorder":
          return p.reorderPoint;
        case "value":
          return p.stockQty * p.unitPriceUsd;
        case "status":
          return stockStatus(p);
      }
    };
    return [...filtered].sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return (av - bv) * dir;
    });
  }, [filtered, sort]);

  const stockValue = items.reduce((s, p) => s + p.stockQty * p.unitPriceUsd, 0);
  const low = items.filter((p) => stockStatus(p) === "low-stock").length;
  const out = items.filter((p) => stockStatus(p) === "out-of-stock").length;
  const statusesPresent = useMemo(
    () => [...new Set(items.map((p) => stockStatus(p)))] as Exclude<StatusFilter, "all">[],
    [items],
  );

  const categorySelected = useMemo(
    () => (categoryId === "all" ? new Set<string>() : new Set([categoryById(categoryId)?.name ?? categoryId])),
    [categoryId],
  );
  const statusSelected = useMemo(
    () => (statusFilter === "all" ? new Set<string>() : new Set([statusFilterLabel[statusFilter]])),
    [statusFilter],
  );

  return (
    <>
      <PageHeader
        eyebrow="Materials catalogue"
        title="Products, prices and stock"
        description="Every SKU held across the Delta Basin warehouses, with unit price, stock on hand and reorder point. Edit any product to see the figures update everywhere on this page."
        actions={
          <button
            type="button"
            onClick={resetCatalog}
            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
          >
            <RotateCcw className="size-3.5" aria-hidden />
            Reset edits
          </button>
        }
      />

      <p className="rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs leading-relaxed text-warning">
        Capability preview — shown to illustrate platform breadth, not yet scoped with CUSTOMER0.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Active SKUs" value={formatNumber(items.length)} delta={`${categories.length} categories`} />
        <Metric label="Stock value" value={formatUsd(stockValue)} delta="Unit price × quantity on hand" />
        <Metric
          label="Below reorder point"
          value={String(low)}
          tone={low > 0 ? "warning" : "positive"}
          delta={statusFilter === "low-stock" ? "Click to clear filter" : "Click to filter the table below"}
          onClick={() => toggleStatusFilter("low-stock")}
          active={statusFilter === "low-stock"}
        />
        <Metric
          label="Out of stock"
          value={String(out)}
          tone={out > 0 ? "critical" : "positive"}
          delta={statusFilter === "out-of-stock" ? "Click to clear filter" : "Click to filter the table below"}
          onClick={() => toggleStatusFilter("out-of-stock")}
          active={statusFilter === "out-of-stock"}
        />
      </div>

      <Panel
        title="Catalogue"
        note={`${filtered.length} of ${items.length} products`}
        actions={
          <ExportCsvButton
            filename="delta-basin-catalogue.csv"
            headers={["SKU", "Product", "Category", "Supplier", "Location", "Unit", "Unit price USD", "Stock", "Reorder point", "Updated"]}
            rows={filtered.map((p) => [
              p.sku,
              p.name,
              categoryById(p.categoryId)?.name ?? p.categoryId,
              p.supplier,
              p.location,
              p.unit,
              p.unitPriceUsd,
              p.stockQty,
              p.reorderPoint,
              p.updatedAt,
            ])}
          />
        }
      >
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name or SKU"
            aria-label="Search products"
            className="w-full max-w-xs rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary/60 sm:w-auto"
          />
          <div className="flex flex-wrap gap-1.5">
            {[{ id: "all", name: "All" }, ...categories].map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => setCategoryId(c.id)}
                className={
                  "rounded-md border px-2.5 py-1.5 text-xs transition-colors " +
                  (categoryId === c.id
                    ? "border-primary/60 bg-primary/10 text-foreground"
                    : "border-border bg-surface text-muted-foreground hover:text-foreground")
                }
              >
                {c.name}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5 border-l border-border pl-2">
            {statusesPresent.map((st) => (
              <button
                key={st}
                type="button"
                onClick={() => toggleStatusFilter(st)}
                className={
                  "rounded-md border px-2.5 py-1.5 text-xs transition-colors " +
                  (statusFilter === st
                    ? "border-primary/60 bg-primary/10 text-foreground"
                    : "border-border bg-surface text-muted-foreground hover:text-foreground")
                }
              >
                {statusFilterLabel[st]}
              </button>
            ))}
          </div>
        </div>

        {sorted.length === 0 ? (
          <EmptyState
            icon={PackageSearch}
            title="No products match this search."
            hint="Clear the search box or pick a different category to see the rest of the catalogue."
          />
        ) : (
        <DataTable
          head={["", "Product", "Category", "Unit price", "Stock", "Reorder", "Value", "Status", "Edit"]}
          headOverride={
            <tr>
              <th className="w-12 border-b border-border" />
              <th className="tabular border-b border-border px-3 py-2 text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Product"
                  align="left"
                  sortDir={sort?.key === "name" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "name", dir })}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Category"
                  sortDir={sort?.key === "category" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "category", dir })}
                  values={categories.map((c) => c.name)}
                  selected={categorySelected}
                  onToggleValue={(v) => {
                    const cat = categories.find((c) => c.name === v);
                    if (cat) setCategoryId((prev) => (prev === cat.id ? "all" : cat.id));
                  }}
                  onClearFilter={() => setCategoryId("all")}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Unit price"
                  sortDir={sort?.key === "unitPrice" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "unitPrice", dir })}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Stock"
                  sortDir={sort?.key === "stock" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "stock", dir })}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Reorder"
                  sortDir={sort?.key === "reorder" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "reorder", dir })}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Value"
                  sortDir={sort?.key === "value" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "value", dir })}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <ColumnMenu
                  label="Status"
                  sortDir={sort?.key === "status" ? sort.dir : null}
                  onSort={(dir) => setSort({ key: "status", dir })}
                  values={statusesPresent.map((st) => statusFilterLabel[st])}
                  selected={statusSelected}
                  onToggleValue={(v) => {
                    const st = statusesPresent.find((s) => statusFilterLabel[s] === v);
                    if (st) toggleStatusFilter(st);
                  }}
                  onClearFilter={() => setStatusFilter("all")}
                />
              </th>
              <th className="tabular whitespace-nowrap border-b border-border px-3 py-2 text-right text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                Edit
              </th>
            </tr>
          }
        >
          {sorted.map((p) => (
            <tr key={p.id} className="border-b border-border/60 last:border-0">
              <td className="px-3 py-2 text-left">
                <ProductPhoto product={p} size={40} />
              </td>
              <td className="px-3 py-2 text-left">
                <span className="block text-foreground">{p.name}</span>
                <span className="tabular block text-[11px] text-muted-foreground">
                  {p.sku} · {p.supplier} · {p.location}
                </span>
              </td>
              <td className="px-3 py-2 text-right text-muted-foreground">
                {categoryById(p.categoryId)?.name}
              </td>
              <td className="tabular px-3 py-2 text-right text-foreground">
                {formatUsd(p.unitPriceUsd)}
                <span className="text-muted-foreground"> /{p.unit}</span>
              </td>
              <td className="tabular px-3 py-2 text-right text-foreground">{formatNumber(p.stockQty)}</td>
              <td className="tabular px-3 py-2 text-right text-muted-foreground">
                {formatNumber(p.reorderPoint)}
              </td>
              <td className="tabular px-3 py-2 text-right text-foreground">
                {formatUsd(p.stockQty * p.unitPriceUsd)}
              </td>
              <td className="px-3 py-2 text-right">
                <StatusPill status={stockStatus(p)} />
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => setEditing(p)}
                  aria-label={`Edit ${p.name}`}
                  className="inline-flex items-center gap-1 rounded-md border border-border bg-surface px-2 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
                >
                  <Pencil className="size-3" aria-hidden />
                  Edit
                </button>
              </td>
            </tr>
          ))}
        </DataTable>
        )}
      </Panel>

      {editing ? (
        <EditProductDialog
          product={editing}
          onClose={() => setEditing(null)}
          onSave={(patch) => {
            updateProduct(editing.id, patch);
            setEditing(null);
          }}
        />
      ) : null}

      <SyntheticNote>
        Synthetic catalogue, pre-discovery. Edits are saved in this browser only so the flow can be tested
        end to end before a real materials system is connected.
      </SyntheticNote>
    </>
  );
}

function EditProductDialog({
  product,
  onClose,
  onSave,
}: {
  product: Product;
  onClose: () => void;
  onSave: (patch: Partial<Product>) => void;
}) {
  const [imageUrl, setImageUrl] = useState<string | undefined>(product.imageUrl);
  const [imageError, setImageError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [form, setForm] = useState({
    name: product.name,
    sku: product.sku,
    categoryId: product.categoryId,
    supplier: product.supplier,
    location: product.location,
    unit: product.unit,
    unitPriceUsd: String(product.unitPriceUsd),
    stockQty: String(product.stockQty),
    reorderPoint: String(product.reorderPoint),
  });

  const field = "w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none focus:border-primary/60";
  const label = "tabular block text-[10px] uppercase tracking-[0.16em] text-muted-foreground";

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-4 sm:items-center"
      role="dialog"
      aria-modal="true"
      aria-label={`Edit ${product.name}`}
      onClick={onClose}
    >
      <form
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          onSave({
            name: form.name.trim() || product.name,
            sku: form.sku.trim() || product.sku,
            categoryId: form.categoryId,
            supplier: form.supplier.trim(),
            location: form.location.trim(),
            unit: form.unit.trim() || product.unit,
            unitPriceUsd: Math.max(0, Number(form.unitPriceUsd) || 0),
            stockQty: Math.max(0, Math.round(Number(form.stockQty) || 0)),
            reorderPoint: Math.max(0, Math.round(Number(form.reorderPoint) || 0)),
            imageUrl,
          });
        }}
        className="max-h-[90vh] w-full max-w-lg overflow-auto rounded-lg border border-border bg-card p-5 shadow-xl"
      >
        <h2 className="font-display text-base font-semibold text-foreground">Edit product</h2>
        <p className="mt-1 text-xs text-muted-foreground">{product.sku}</p>

        <div className="mt-4 flex items-center gap-3 rounded-md border border-border bg-surface p-3">
          <ProductPhoto product={{ name: form.name, imageUrl }} size={72} />
          <div className="min-w-0">
            <span className={label}>Photo</span>
            <div className="mt-1.5 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => fileInput.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
              >
                <ImagePlus className="size-3.5" aria-hidden />
                {imageUrl ? "Replace photo" : "Upload photo"}
              </button>
              {imageUrl ? (
                <button
                  type="button"
                  onClick={() => setImageUrl(undefined)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface-2 px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-critical/60 hover:text-foreground"
                >
                  <Trash2 className="size-3.5" aria-hidden />
                  Remove
                </button>
              ) : null}
            </div>
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              {imageError ?? "JPG or PNG. Saved in this browser with the product."}
            </p>
            <input
              ref={fileInput}
              type="file"
              accept="image/*"
              aria-label="Product photo"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                e.target.value = "";
                if (!file) return;
                try {
                  setImageError(null);
                  setImageUrl(await fileToThumbnailDataUrl(file));
                } catch {
                  setImageError("That image could not be read. Try another file.");
                }
              }}
            />
          </div>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <label className="sm:col-span-2">
            <span className={label}>Name</span>
            <input className={field} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
          </label>
          <label>
            <span className={label}>SKU</span>
            <input className={field} value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })} />
          </label>
          <label>
            <span className={label}>Category</span>
            <select
              className={field}
              value={form.categoryId}
              onChange={(e) => setForm({ ...form, categoryId: e.target.value })}
            >
              {categories.map((c) => (
                <option key={c.id} value={c.id} className="bg-surface text-foreground">
                  {c.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className={label}>Supplier</span>
            <input className={field} value={form.supplier} onChange={(e) => setForm({ ...form, supplier: e.target.value })} />
          </label>
          <label>
            <span className={label}>Location</span>
            <input className={field} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} />
          </label>
          <label>
            <span className={label}>Unit</span>
            <input className={field} value={form.unit} onChange={(e) => setForm({ ...form, unit: e.target.value })} />
          </label>
          <label>
            <span className={label}>Unit price (USD)</span>
            <input
              type="number"
              min={0}
              step="0.01"
              className={field}
              value={form.unitPriceUsd}
              onChange={(e) => setForm({ ...form, unitPriceUsd: e.target.value })}
            />
          </label>
          <label>
            <span className={label}>Stock on hand</span>
            <input
              type="number"
              min={0}
              className={field}
              value={form.stockQty}
              onChange={(e) => setForm({ ...form, stockQty: e.target.value })}
            />
          </label>
          <label>
            <span className={label}>Reorder point</span>
            <input
              type="number"
              min={0}
              className={field}
              value={form.reorderPoint}
              onChange={(e) => setForm({ ...form, reorderPoint: e.target.value })}
            />
          </label>
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-border bg-surface px-3 py-2 text-sm text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="rounded-md border border-primary/60 bg-primary/15 px-3 py-2 text-sm text-foreground hover:bg-primary/25"
          >
            Save changes
          </button>
        </div>
      </form>
    </div>
  );
}
