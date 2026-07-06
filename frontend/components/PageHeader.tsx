export function PageHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <header className="mb-6">
      <p className="text-sm font-semibold uppercase tracking-wide text-accent">AdOps Signal</p>
      <h1 className="mt-1 text-2xl font-semibold tracking-normal text-ink md:text-3xl">{title}</h1>
      <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">{subtitle}</p>
    </header>
  );
}
