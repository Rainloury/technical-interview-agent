export function LoadingRows({ rows = 4 }: { rows?: number }) {
  return (
    <div className="loading-rows" role="status" aria-label="正在加载">
      {Array.from({ length: rows }, (_, index) => (
        <div className="loading-row" key={index}>
          <span className="skeleton skeleton--title" />
          <span className="skeleton skeleton--meta" />
        </div>
      ))}
    </div>
  );
}
