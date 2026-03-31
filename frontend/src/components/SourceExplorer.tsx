import type { EngagementStats, TaskItem } from "../api/types";

interface Props {
  stats: EngagementStats | undefined;
  timeline: TaskItem[] | undefined;
}

export default function SourceExplorer({ stats, timeline }: Props) {
  if (!stats?.source_configs?.length) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-700">Sources</h3>
        <p className="text-xs text-gray-400">No sources configured</p>
      </div>
    );
  }

  // Count tasks per source_type
  const taskCounts: Record<string, Record<string, number>> = {};
  for (const task of timeline ?? []) {
    const key = task.source_type;
    if (!taskCounts[key]) taskCounts[key] = {};
    taskCounts[key][task.status] = (taskCounts[key][task.status] ?? 0) + 1;
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">Sources</h3>
      <div className="space-y-3">
        {stats.source_configs.map((sc, i) => {
          const counts = taskCounts[sc.source_type] ?? {};
          const total = Object.values(counts).reduce((a, b) => a + b, 0);
          const completed = counts["completed"] ?? 0;
          const ref =
            (sc.config as Record<string, string>).path ||
            (sc.config as Record<string, string>).url ||
            sc.source_type;

          return (
            <div key={i} className="rounded border border-gray-100 p-2">
              <div className="flex items-center gap-2">
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 uppercase">
                  {sc.source_type}
                </span>
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    sc.status === "verified" ? "bg-green-400" : "bg-gray-300"
                  }`}
                />
              </div>
              <p className="mt-1 truncate text-xs text-gray-500">{String(ref)}</p>
              {total > 0 && (
                <div className="mt-1 flex gap-2 text-[10px] text-gray-400">
                  <span>{completed}/{total} tasks done</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
