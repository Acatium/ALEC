import type { ConsolidatedUnit } from "../api/types";

export default function KeyFindings({
  data,
}: {
  data: ConsolidatedUnit[] | undefined;
}) {
  if (!data || data.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-700">
          Key Findings
        </h3>
        <p className="text-xs text-gray-400">
          No consolidated summaries yet. These appear after consolidation runs.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">Key Findings</h3>
      <div className="space-y-3">
        {data.map((unit) => (
          <div
            key={unit.unit_id}
            className="rounded border border-gray-100 p-3"
          >
            {unit.subject_entity_name && (
              <div className="mb-1 text-xs font-medium text-indigo-600">
                {unit.subject_entity_name}
              </div>
            )}
            <p className="text-sm text-gray-700 whitespace-pre-line">
              {unit.summary}
            </p>
            <div className="mt-1 flex gap-2 text-[10px] text-gray-400">
              <span>v{unit.version}</span>
              <span>{unit.token_count} tokens</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
