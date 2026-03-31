import { Link } from "react-router-dom";
import { useEngagements } from "../api/hooks";
import StatusBadge from "./StatusBadge";

export default function EngagementList() {
  const { data, isLoading, error } = useEngagements();

  if (isLoading) return <p className="text-sm text-gray-500">Loading...</p>;
  if (error)
    return <p className="text-sm text-red-600">Error: {String(error)}</p>;
  if (!data || data.length === 0)
    return (
      <p className="text-sm text-gray-500">
        No engagements yet. Create one to get started.
      </p>
    );

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {data.map((eng) => (
        <Link
          key={eng.engagement_id}
          to={`/engagements/${eng.engagement_id}`}
          className="block rounded-lg border border-gray-200 bg-white p-4 shadow-sm hover:shadow-md transition-shadow"
        >
          <div className="flex items-start justify-between">
            <h3 className="text-sm font-medium text-gray-900 truncate pr-2">
              {eng.name}
            </h3>
            <StatusBadge status={eng.status} />
          </div>
          {(eng.summary || eng.problem_statement) && (
            <p className="mt-1 text-xs text-gray-500 line-clamp-2">
              {eng.summary || eng.problem_statement}
            </p>
          )}
          <div className="mt-3 flex gap-4 text-xs text-gray-500">
            <span>{eng.entity_count} entities</span>
            <span>{eng.relationship_count} rels</span>
            <span>{eng.observation_count} obs</span>
          </div>
          {eng.status === "stalled" && (
            <div className="mt-2 text-xs text-amber-600">
              Stalled — click to resume
            </div>
          )}
        </Link>
      ))}
    </div>
  );
}
