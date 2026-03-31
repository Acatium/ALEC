import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import {
  useEngagement,
  useWebSocket,
  useDeleteEngagement,
  useRestartEngagement,
  useStats,
  useTimeline,
  useConsolidated,
  useUpdateEngagement,
} from "../api/hooks";
import StatusBadge from "./StatusBadge";
import StatsBar from "./StatsBar";
import ConvergenceChart from "./ConvergenceChart";
import KnowledgeGraph from "./KnowledgeGraph";
import KeyFindings from "./KeyFindings";
import SourceManager from "./SourceManager";
import QuestionsPanel from "./QuestionsPanel";
import DirectiveCreator from "./DirectiveCreator";
import ActivityTimeline from "./ActivityTimeline";
import SnapshotsPanel from "./SnapshotsPanel";
import ObservationBreakdown from "./ObservationBreakdown";
import SchemaEditor from "./SchemaEditor";

export default function EngagementDashboard({ id }: { id: string }) {
  const { data: engagement, isLoading } = useEngagement(id);
  const { data: stats } = useStats(id);
  const { data: timeline } = useTimeline(id);
  const { data: consolidated } = useConsolidated(id);
  const { events } = useWebSocket(id);
  const navigate = useNavigate();
  const deleteMutation = useDeleteEngagement();
  const restartMutation = useRestartEngagement();

  const updateEngagement = useUpdateEngagement();

  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [editingSummary, setEditingSummary] = useState(false);
  const [summaryValue, setSummaryValue] = useState("");
  const [editingProblem, setEditingProblem] = useState(false);
  const [problemValue, setProblemValue] = useState("");

  const handleSaveName = () => {
    if (nameValue.trim() && nameValue !== engagement?.name) {
      updateEngagement.mutate({ id, data: { name: nameValue.trim() } });
    }
    setEditingName(false);
  };

  const handleSaveSummary = () => {
    if (summaryValue !== engagement?.summary) {
      updateEngagement.mutate({
        id,
        data: { summary: summaryValue },
      });
    }
    setEditingSummary(false);
  };

  const handleSaveProblem = () => {
    if (problemValue !== engagement?.problem_statement) {
      updateEngagement.mutate({
        id,
        data: { problem_statement: problemValue },
      });
    }
    setEditingProblem(false);
  };

  const canRestart =
    engagement?.status === "error" ||
    engagement?.status === "completed" ||
    engagement?.status === "converged" ||
    engagement?.status === "stalled";
  const canDelete =
    engagement?.status !== "active" && engagement?.status !== "stalled";
  const isActive = engagement?.status === "active";

  if (isLoading) return <p className="text-sm text-gray-500">Loading...</p>;
  if (!engagement) return <p className="text-sm text-red-600">Not found</p>;

  return (
    <div className="space-y-4">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          {editingName ? (
            <input
              value={nameValue}
              onChange={(e) => setNameValue(e.target.value)}
              onBlur={handleSaveName}
              onKeyDown={(e) => e.key === "Enter" && handleSaveName()}
              className="min-w-0 text-lg font-bold text-gray-900 border-b-2 border-indigo-300 outline-none bg-transparent flex-1"
              autoFocus
            />
          ) : (
            <h1
              className="min-w-0 text-lg font-bold text-gray-900 truncate cursor-pointer hover:text-indigo-600"
              onClick={() => {
                setNameValue(engagement.name);
                setEditingName(true);
              }}
              title="Click to edit"
            >
              {engagement.name}
            </h1>
          )}
          <StatusBadge status={engagement.status} />
          <div className="ml-auto flex shrink-0 gap-2">
            {canRestart && (
              <button
                onClick={() => restartMutation.mutate(id)}
                disabled={restartMutation.isPending}
                className="rounded bg-blue-600 px-3 py-1 text-sm text-white hover:bg-blue-700 disabled:opacity-50"
              >
                {restartMutation.isPending
                  ? "Continuing..."
                  : engagement.status === "stalled"
                    ? "Resume"
                    : "Continue"}
              </button>
            )}
            {canDelete && (
              <button
                onClick={() => {
                  if (confirm("Delete this engagement and all its data?")) {
                    deleteMutation.mutate(id, {
                      onSuccess: () => navigate("/"),
                    });
                  }
                }}
                disabled={deleteMutation.isPending}
                className="rounded bg-red-600 px-3 py-1 text-sm text-white hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </button>
            )}
          </div>
        </div>
        {editingSummary ? (
          <textarea
            value={summaryValue}
            onChange={(e) => setSummaryValue(e.target.value)}
            onBlur={handleSaveSummary}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSaveSummary();
              }
            }}
            rows={2}
            className="mt-1 w-full text-sm text-gray-600 border border-indigo-200 rounded px-2 py-1 outline-none focus:border-indigo-400"
            autoFocus
          />
        ) : (
          (engagement.summary || engagement.problem_statement) && (
            <p
              className="mt-1 text-sm text-gray-600 cursor-pointer hover:text-indigo-600"
              onClick={() => {
                setSummaryValue(engagement.summary || engagement.problem_statement || "");
                setEditingSummary(true);
              }}
              title="Click to edit summary"
            >
              {engagement.summary || engagement.problem_statement}
            </p>
          )
        )}
        {engagement.problem_statement && (
          <div className="mt-2">
            <span className="text-xs font-medium text-gray-400 uppercase tracking-wide">Initial Prompt</span>
            {editingProblem ? (
              <textarea
                value={problemValue}
                onChange={(e) => setProblemValue(e.target.value)}
                onBlur={handleSaveProblem}
                rows={2}
                className="mt-0.5 w-full text-xs text-gray-500 border border-indigo-200 rounded px-2 py-1 outline-none focus:border-indigo-400"
                autoFocus
              />
            ) : (
              <p
                className="mt-0.5 text-xs text-gray-500 cursor-pointer hover:text-indigo-600"
                onClick={() => {
                  setProblemValue(engagement.problem_statement || "");
                  setEditingProblem(true);
                }}
                title="Click to edit initial prompt"
              >
                {engagement.problem_statement}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Stalled banner */}
      {engagement.status === "stalled" && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-800">
            This engagement appears stalled — the supervisor has stopped
            sending heartbeats. Click Resume to restart it.
          </p>
        </div>
      )}

      {/* Stats row */}
      <StatsBar data={stats} />

      {/* Two-column grid */}
      <div className="grid gap-4 lg:grid-cols-[2fr_1fr]">
        {/* Left column (wider) */}
        <div className="space-y-4">
          <ConvergenceChart
            data={stats?.convergence_history ?? []}
          />
          <KnowledgeGraph
            engagementId={id}
            selectedEntityId={selectedEntityId}
            onSelectEntity={setSelectedEntityId}
          />
          <KeyFindings data={consolidated} />
        </div>

        {/* Right column (narrower) */}
        <div className="space-y-4">
          <SchemaEditor engagementId={id} />
          <SourceManager engagementId={id} />
          <QuestionsPanel engagementId={id} />
          <DirectiveCreator engagementId={id} />
          <ActivityTimeline
            tasks={timeline}
            events={events}
            isActive={isActive}
          />
          <SnapshotsPanel engagementId={id} />
          <ObservationBreakdown
            data={stats?.observation_type_breakdown}
          />
        </div>
      </div>

      {/* Footer */}
      <div className="text-center pt-2">
        <Link
          to={`/engagements/${id}/report`}
          className="text-sm text-indigo-600 hover:text-indigo-800 hover:underline"
        >
          View Report
        </Link>
      </div>
    </div>
  );
}
