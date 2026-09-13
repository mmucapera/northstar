import { Package } from "lucide-react";
import type { Product } from "@/data/catalog";

const swatchByCategory: Record<string, string> = {
  drilling: "border-primary/40 bg-primary/10 text-primary",
  wellhead: "border-positive/40 bg-positive/10 text-positive",
  rotating: "border-warning/40 bg-warning/10 text-warning",
  electrical: "border-critical/40 bg-critical/10 text-critical",
  ppe: "border-primary/40 bg-primary/10 text-primary",
  pipeline: "border-warning/40 bg-warning/10 text-warning",
};

export function ProductPhoto({
  product,
  size = 40,
  className = "",
}: {
  product: Pick<Product, "name" | "imageUrl"> & Partial<Pick<Product, "sku" | "categoryId">>;
  size?: number;
  className?: string;
}) {
  const base =
    "shrink-0 overflow-hidden rounded-md border border-border bg-surface-2 " + className;
  if (!product.imageUrl) {
    const tone =
      (product.categoryId && swatchByCategory[product.categoryId]) ??
      "border-border bg-surface-2 text-muted-foreground";
    return (
      <div
        className={base + " flex items-center justify-center " + tone}
        style={{ width: size, height: size }}
        role="img"
        aria-label={`No photo yet for ${product.name}`}
        title={product.name}
      >
        <Package className="size-[55%]" aria-hidden />
      </div>
    );
  }
  return (
    <img
      src={product.imageUrl}
      alt={`Photo of ${product.name}`}
      loading="lazy"
      width={size}
      height={size}
      className={base + " object-cover"}
      style={{ width: size, height: size }}
    />
  );
}
