import type { TaskItem, ALECEvent } from "../api/types";

const statusColors: Record<string, string> = {
  completed: "bg-green-400",
  failed: "bg-red-400",
  running: "bg-blue-400 animate-pulse",
  assigned: "bg-yellow-400",
  queued: "bg-gray-300",
};

function formatTime(iso: string | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

interface Props {
  tasks: TaskItem[] | undefined;
  events: ALECEvent[];
  isActive: boolean;
}

export default function ActivityTimeline({ tasks, events, isActive }: Props) {
  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">Activity</h3>

      {/* Live events pulse (only during active runs) */}
      {isActive && events.length > 0 && (
        <div className="mb-3 rounded border border-blue-100 bg-blue-50 p-2">
          <div className="mb-1 text-[10px] font-medium text-blue-600 uppercase">
            Live
          </div>
          {events.slice(-3).reverse().map((ev, i) => (
            <div key={i} className="text-xs text-blue-700 truncate">
              {ev.event_type}
              {ev.worker_id ? ` (${String(ev.worker_id)})` : ""}
            </div>
          ))}
        </div>
      )}

      {/* Task list from DB */}
      <div className="space-y-2 max-h-80 overflow-y-auto">
        {(!tasks || tasks.length === 0) && (
          <p className="text-xs text-gray-400">No tasks yet</p>
        )}
        {tasks
          ?.slice()
          .reverse()
          .map((task) => (
            <div
              key={task.task_id}
              className="flex items-start gap-2 rounded border border-gray-100 p-2"
            >
              <span
                className={`mt-1 h-2 w-2 shrink-0 rounded-full ${
                  statusColors[task.status] ?? "bg-gray-300"
                }`}
              />
              <div className="min-w-0 flex-1">
                <p className="text-xs text-gray-700 line-clamp-2">
                  {task.directive}
                </p>
                <div className="mt-0.5 flex gap-2 text-[10px] text-gray-400">
                  <span>{task.source_type}</span>
                  <span>{task.status}</span>
                  {task.created_at && <span>{formatTime(task.created_at)}</span>}
                </div>
                {task.result_summary && (
                  <div className="mt-0.5 text-[10px] text-gray-400">
                    {task.result_summary.entities_written != null && (
                      <span>
                        +{String(task.result_summary.entities_written)} entities,{" "}
                        +{String(task.result_summary.relationships_written)} rels
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
      </div>
    </div>
  );
}
