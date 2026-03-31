import { useState } from "react";
import {
  useSources,
  useAddSource,
  useUpdateSource,
  useDeleteSource,
} from "../api/hooks";

const TRUST_TIERS = ["authoritative", "analytical", "reference"] as const;

const TRUST_COLORS: Record<string, string> = {
  authoritative: "bg-green-100 text-green-700",
  analytical: "bg-blue-100 text-blue-700",
  reference: "bg-gray-100 text-gray-600",
};

interface Props {
  engagementId: string;
}

export default function SourceManager({ engagementId }: Props) {
  const { data: sources } = useSources(engagementId);
  const addSource = useAddSource();
  const updateSource = useUpdateSource();
  const deleteSource = useDeleteSource();

  const [newSource, setNewSource] = useState("");

  const handleAdd = () => {
    const trimmed = newSource.trim();
    if (!trimmed) return;
    addSource.mutate(
      { engagementId, source: trimmed },
      { onSuccess: () => setNewSource("") },
    );
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">Sources</h3>

      {(!sources || sources.length === 0) && (
        <p className="mb-3 text-xs text-gray-400">No sources configured</p>
      )}

      <div className="space-y-2">
        {sources?.map((sc) => {
          const ref =
            (sc.config as Record<string, string>).base_path ||
            (sc.config as Record<string, string>).seed_url ||
            sc.source_type;
          const isDisabled = sc.status === "disabled";

          return (
            <div
              key={sc.source_config_id}
              className={`rounded border p-2 ${isDisabled ? "border-gray-100 bg-gray-50 opacity-60" : "border-gray-200"}`}
            >
              <div className="flex items-center gap-2">
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600 uppercase">
                  {sc.source_type}
                </span>
                <span
                  className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${TRUST_COLORS[sc.trust_tier] || TRUST_COLORS.reference}`}
                >
                  {sc.trust_tier}
                </span>
                <span
                  className={`ml-auto h-1.5 w-1.5 rounded-full ${
                    sc.status === "verified"
                      ? "bg-green-400"
                      : sc.status === "disabled"
                        ? "bg-gray-300"
                        : "bg-yellow-400"
                  }`}
                />
              </div>

              <p className="mt-1 truncate text-xs text-gray-500">
                {String(ref)}
              </p>

              <div className="mt-2 flex items-center gap-2">
                {/* Priority slider */}
                <label className="flex items-center gap-1 text-[10px] text-gray-400">
                  Pri:
                  <input
                    type="range"
                    min={1}
                    max={100}
                    value={sc.priority}
                    onChange={(e) =>
                      updateSource.mutate({
                        engagementId,
                        sourceConfigId: sc.source_config_id,
                        data: { priority: Number(e.target.value) },
                      })
                    }
                    className="h-1 w-16 accent-indigo-500"
                  />
                  <span className="w-5 text-center">{sc.priority}</span>
                </label>

                {/* Trust tier dropdown */}
                <select
                  value={sc.trust_tier}
                  onChange={(e) =>
                    updateSource.mutate({
                      engagementId,
                      sourceConfigId: sc.source_config_id,
                      data: { trust_tier: e.target.value },
                    })
                  }
                  className="rounded border border-gray-200 px-1 py-0.5 text-[10px] text-gray-600"
                >
                  {TRUST_TIERS.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>

                {/* Disable/Enable */}
                <button
                  onClick={() =>
                    updateSource.mutate({
                      engagementId,
                      sourceConfigId: sc.source_config_id,
                      data: {
                        status: isDisabled ? "verified" : "disabled",
                      },
                    })
                  }
                  className="text-[10px] text-gray-400 hover:text-gray-600"
                >
                  {isDisabled ? "Enable" : "Disable"}
                </button>

                {/* Remove */}
                <button
                  onClick={() => {
                    if (confirm("Remove this source?")) {
                      deleteSource.mutate({
                        engagementId,
                        sourceConfigId: sc.source_config_id,
                      });
                    }
                  }}
                  className="text-[10px] text-red-400 hover:text-red-600"
                >
                  Remove
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add source */}
      <div className="mt-3 flex gap-2">
        <input
          type="text"
          value={newSource}
          onChange={(e) => setNewSource(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAdd()}
          placeholder="web:https://... or ./path"
          className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-300 focus:outline-none"
        />
        <button
          onClick={handleAdd}
          disabled={addSource.isPending || !newSource.trim()}
          className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Add
        </button>
      </div>
    </div>
  );
}
