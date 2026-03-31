import type { EngagementStats } from "../api/types";

const stats: { key: keyof EngagementStats; label: string }[] = [
  { key: "entity_count", label: "Entities" },
  { key: "relationship_count", label: "Relationships" },
  { key: "observation_count", label: "Observations" },
  { key: "cycle_count", label: "Cycles" },
  { key: "task_count", label: "Tasks" },
];

export default function StatsBar({ data }: { data: EngagementStats | undefined }) {
  if (!data) return null;

  const lastConv = data.convergence_history[data.convergence_history.length - 1];
  const ratio = lastConv?.ratio;

  return (
    <div className="grid grid-cols-3 gap-3 sm:grid-cols-6">
      {stats.map((s) => (
        <div
          key={s.key}
          className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-center"
        >
          <div className="text-lg font-bold text-gray-900">
            {data[s.key] as number}
          </div>
          <div className="text-xs text-gray-500">{s.label}</div>
        </div>
      ))}
      <div className="rounded-lg border border-gray-200 bg-white px-3 py-2 text-center">
        <div className="text-lg font-bold text-gray-900">
          {ratio != null ? ratio.toFixed(2) : "--"}
        </div>
        <div className="text-xs text-gray-500">Convergence</div>
      </div>
    </div>
  );
}
