import type { ALECEvent } from "../api/types";

export default function CycleProgress({ events }: { events: ALECEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="text-sm text-gray-400">
        Waiting for events...
      </p>
    );
  }

  return (
    <div className="space-y-2">
      {events
        .slice()
        .reverse()
        .map((ev, i) => {
          const workerId = ev.worker_id ? String(ev.worker_id) : null;
          const action = ev.current_action ? String(ev.current_action) : null;
          return (
            <div
              key={i}
              className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm"
            >
              <div className="flex items-center justify-between">
                <span className="font-medium text-gray-700">
                  {ev.event_type}
                </span>
                <span className="text-xs text-gray-400">
                  {new Date(ev.timestamp).toLocaleTimeString()}
                </span>
              </div>
              {workerId && (
                <span className="text-xs text-gray-500">{workerId}</span>
              )}
              {action && (
                <p className="mt-1 text-xs text-gray-500">{action}</p>
              )}
            </div>
          );
        })}
    </div>
  );
}
