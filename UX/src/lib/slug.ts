// URL-safe slugs for region names ("US Gulf" -> "us-gulf") used to link
// between the region list views and the /inventory/$region detail route.

export function slugifyRegion(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

export function findRegionBySlug<T extends { name: string }>(
  rows: T[],
  slug: string,
): T | undefined {
  return rows.find((r) => slugifyRegion(r.name) === slug);
}
