import { useState } from "react";
import { useSnapshots, useCreateSnapshot, useStats } from "../api/hooks";

interface Props {
  engagementId: string;
}

export default function SnapshotsPanel({ engagementId }: Props) {
  const { data: snapshots } = useSnapshots(engagementId);
  const { data: stats } = useStats(engagementId);
  const createSnapshot = useCreateSnapshot();

  const [name, setName] = useState("");
  const [showForm, setShowForm] = useState(false);

  const handleCreate = () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    createSnapshot.mutate(
      { engagementId, data: { name: trimmed } },
      {
        onSuccess: () => {
          setName("");
          setShowForm(false);
        },
      },
    );
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-700">Snapshots</h3>
        {!showForm && (
          <button
            onClick={() => setShowForm(true)}
            className="rounded bg-gray-100 px-2 py-0.5 text-[10px] text-gray-600 hover:bg-gray-200"
          >
            Take Snapshot
          </button>
        )}
      </div>

      {showForm && (
        <div className="mb-3 flex gap-2">
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
            placeholder="Snapshot name..."
            className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-300 focus:outline-none"
            autoFocus
          />
          <button
            onClick={handleCreate}
            disabled={createSnapshot.isPending || !name.trim()}
            className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Save
          </button>
          <button
            onClick={() => setShowForm(false)}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Cancel
          </button>
        </div>
      )}

      <div className="space-y-2 max-h-48 overflow-y-auto">
        {snapshots?.map((s) => {
          const diffE = stats
            ? stats.entity_count - s.entity_count
            : 0;
          return (
            <div
              key={s.snapshot_id}
              className="rounded border border-gray-100 p-2"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-700">
                  {s.name}
                </span>
                <span className="text-[10px] text-gray-400">
                  {new Date(s.created_at).toLocaleDateString()}
                </span>
              </div>
              <div className="mt-1 flex flex-wrap gap-2 text-[10px] text-gray-500">
                <span>{s.entity_count} entities</span>
                <span>{s.relationship_count} rels</span>
                <span>{s.observation_count} obs</span>
                <span>{s.cycle_count} cycles</span>
                {s.convergence_ratio != null && (
                  <span>ratio: {s.convergence_ratio.toFixed(2)}</span>
                )}
              </div>
              {diffE !== 0 && (
                <div className="mt-1 text-[10px]">
                  <span
                    className={
                      diffE > 0 ? "text-green-600" : "text-red-500"
                    }
                  >
                    {diffE > 0 ? "+" : ""}
                    {diffE} entities since snapshot
                  </span>
                </div>
              )}
            </div>
          );
        })}
        {(!snapshots || snapshots.length === 0) && (
          <p className="text-xs text-gray-400">No snapshots yet</p>
        )}
      </div>
    </div>
  );
}
