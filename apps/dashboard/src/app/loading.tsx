/** Route-level loading skeleton — shimmer rows matching the default list layout. */

export default function Loading() {
  return (
    <div className="page" role="status" aria-busy="true" aria-label="Loading">
      <div className="skeleton-row" style={{ maxWidth: "28rem" }}>
        <span className="skeleton" style={{ height: "1.6rem", width: "60%" }} />
        <span className="skeleton" style={{ width: "80%" }} />
      </div>
      {Array.from({ length: 4 }).map((_, i) => (
        <div className="skeleton-row" key={i}>
          <span className="skeleton" style={{ width: `${96 - i * 7}%` }} />
          <span className="skeleton" style={{ width: `${70 - i * 5}%` }} />
        </div>
      ))}
    </div>
  );
}
