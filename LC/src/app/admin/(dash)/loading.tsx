export default function AdminLoading() {
  return (
    <div className="space-y-4">
      <div className="h-9 w-56 animate-pulse rounded bg-sand" />
      <div className="grid gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-[var(--radius-lg)] bg-sand/70" />
        ))}
      </div>
      <div className="h-80 animate-pulse rounded-[var(--radius-lg)] bg-sand/50" />
    </div>
  );
}
