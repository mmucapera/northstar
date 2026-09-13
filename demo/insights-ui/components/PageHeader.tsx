export function PageHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header className="mb-8">
      <div className="text-xs font-medium uppercase tracking-wide text-series-1">{eyebrow}</div>
      <h1 className="mt-1 text-2xl font-semibold text-ink-primary">{title}</h1>
      <p className="mt-1.5 max-w-2xl text-sm text-ink-secondary">{description}</p>
    </header>
  );
}
