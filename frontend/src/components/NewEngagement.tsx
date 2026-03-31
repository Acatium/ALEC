import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateEngagement, useAnalyzeEngagement } from "../api/hooks";
import type { AnalyzeResponse } from "../api/types";

const inputClass =
  "mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500";

function CoveragePill({ level }: { level: string }) {
  const colors: Record<string, string> = {
    full: "bg-green-100 text-green-800",
    partial: "bg-yellow-100 text-yellow-800",
    none: "bg-red-100 text-red-800",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[level] ?? colors.none}`}
    >
      {level}
    </span>
  );
}

function ImportanceBadge({ importance }: { importance: string }) {
  const colors: Record<string, string> = {
    critical: "bg-red-50 text-red-700 ring-red-600/10",
    high: "bg-orange-50 text-orange-700 ring-orange-600/10",
    medium: "bg-blue-50 text-blue-700 ring-blue-600/10",
  };
  return (
    <span
      className={`inline-block rounded-md px-1.5 py-0.5 text-xs font-medium ring-1 ring-inset ${colors[importance] ?? colors.medium}`}
    >
      {importance}
    </span>
  );
}

export default function NewEngagement() {
  const [name, setName] = useState("");
  const [summary, setSummary] = useState("");
  const [sources, setSources] = useState("");
  const [problem, setProblem] = useState("");
  const [cycles, setCycles] = useState(3);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);
  const navigate = useNavigate();
  const createMutation = useCreateEngagement();
  const analyzeMutation = useAnalyzeEngagement();

  const getSourceList = () =>
    sources
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);

  const handleAnalyze = () => {
    if (!problem.trim()) return;
    analyzeMutation.mutate(
      { problem_statement: problem, sources: getSourceList() },
      { onSuccess: (data) => setAnalysis(data) },
    );
  };

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    const sourceList = getSourceList();
    if (sourceList.length === 0) return;
    createMutation.mutate(
      {
        sources: sourceList,
        problem_statement: problem || undefined,
        max_cycles: cycles,
        name: name || undefined,
        summary: summary || undefined,
      },
      { onSuccess: (data) => navigate(`/engagements/${data.engagement_id}`) },
    );
  };

  const addSource = (url: string) => {
    const entry = `web:${url}`;
    const current = getSourceList();
    if (current.includes(entry)) return;
    setSources((prev) => (prev.trim() ? prev.trim() + "\n" + entry : entry));
  };

  return (
    <div className="max-w-3xl space-y-6">
      {/* --- Form --- */}
      <form onSubmit={handleCreate} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700">
            Name
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className={inputClass}
            placeholder="e.g. Q1 Market Analysis (optional — auto-generated if blank)"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Summary
          </label>
          <input
            type="text"
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            className={inputClass}
            placeholder="Human-readable description (optional — defaults to initial prompt)"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Initial Prompt
          </label>
          <input
            type="text"
            value={problem}
            onChange={(e) => setProblem(e.target.value)}
            className={inputClass}
            placeholder="e.g. Develop a data platform strategy for a global banking institution"
            required
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Sources (one per line)
          </label>
          <textarea
            value={sources}
            onChange={(e) => setSources(e.target.value)}
            rows={4}
            className={inputClass}
            placeholder={"./docs/design\nweb:https://example.com"}
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700">
            Max Cycles
          </label>
          <input
            type="number"
            value={cycles}
            onChange={(e) => setCycles(Number(e.target.value))}
            min={1}
            max={20}
            className="mt-1 block w-24 rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={analyzeMutation.isPending || !problem.trim()}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
          >
            {analyzeMutation.isPending ? "Analyzing..." : "Analyze"}
          </button>
          <button
            type="submit"
            disabled={createMutation.isPending}
            className="text-sm text-gray-500 underline hover:text-gray-700"
          >
            {createMutation.isPending ? "Creating..." : "Skip & Create"}
          </button>
        </div>

        {(analyzeMutation.isError || createMutation.isError) && (
          <p className="text-sm text-red-600">
            {String(analyzeMutation.error ?? createMutation.error)}
          </p>
        )}
      </form>

      {/* --- Analysis Results --- */}
      {analysis && (
        <div className="space-y-5 border-t pt-5">
          {/* Overall Assessment */}
          <div className="rounded-md border border-amber-300 bg-amber-50 p-4">
            <h3 className="text-sm font-semibold text-amber-800">
              Overall Assessment
            </h3>
            <p className="mt-1 text-sm text-amber-700">
              {analysis.overall_assessment}
            </p>
          </div>

          {/* Topic Coverage Grid */}
          {analysis.topics.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700">
                Topic Coverage
              </h3>
              <div className="mt-2 overflow-hidden rounded-md border">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-3 py-2 text-left font-medium text-gray-600">
                        Topic
                      </th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600">
                        Importance
                      </th>
                      <th className="px-3 py-2 text-left font-medium text-gray-600">
                        Coverage
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {analysis.topics.map((t) => (
                      <tr key={t.topic}>
                        <td className="px-3 py-2">
                          <div className="font-medium text-gray-900">
                            {t.topic}
                          </div>
                          {t.description && (
                            <div className="text-xs text-gray-500">
                              {t.description}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2">
                          <ImportanceBadge importance={t.importance} />
                        </td>
                        <td className="px-3 py-2">
                          <CoveragePill level={t.coverage_level} />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Gaps */}
          {analysis.gaps.length > 0 && (
            <div className="rounded-md border border-red-300 bg-red-50 p-4">
              <h3 className="text-sm font-semibold text-red-800">Gaps</h3>
              <ul className="mt-1 list-inside list-disc text-sm text-red-700">
                {analysis.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested Sources */}
          {analysis.suggested_sources.length > 0 && (
            <div>
              <h3 className="text-sm font-semibold text-gray-700">
                Suggested Sources
              </h3>
              <div className="mt-2 grid gap-3">
                {analysis.suggested_sources.map((s) => (
                  <div
                    key={s.url}
                    className="flex items-start justify-between rounded-md border p-3"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-gray-900">
                          {s.title || s.url}
                        </span>
                        <span
                          className={`inline-block rounded-full px-1.5 py-0.5 text-xs ${s.reachable ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}
                        >
                          {s.reachable ? "reachable" : "unreachable"}
                        </span>
                      </div>
                      <div className="truncate text-xs text-gray-500">
                        {s.url}
                      </div>
                      {s.reason && (
                        <div className="mt-1 text-xs text-gray-600">
                          {s.reason}
                        </div>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => addSource(s.url)}
                      className="ml-3 shrink-0 rounded bg-blue-50 px-2 py-1 text-xs font-medium text-blue-700 hover:bg-blue-100"
                    >
                      + Add
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-3 border-t pt-4">
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={analyzeMutation.isPending || !problem.trim()}
              className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 disabled:opacity-50"
            >
              {analyzeMutation.isPending ? "Analyzing..." : "Re-analyze"}
            </button>
            <button
              type="button"
              onClick={() => {
                const sourceList = getSourceList();
                if (sourceList.length === 0) return;
                createMutation.mutate(
                  {
                    sources: sourceList,
                    problem_statement: problem || undefined,
                    max_cycles: cycles,
                    name: name || undefined,
                    summary: summary || undefined,
                  },
                  {
                    onSuccess: (data) =>
                      navigate(`/engagements/${data.engagement_id}`),
                  },
                );
              }}
              disabled={createMutation.isPending || getSourceList().length === 0}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {createMutation.isPending
                ? "Creating..."
                : "Create Engagement"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
