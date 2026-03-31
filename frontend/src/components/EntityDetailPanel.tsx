import { useState } from "react";
import {
  useEntityDetail,
  useAnnotations,
  useCreateAnnotation,
  useDeleteAnnotation,
  useUpdateEntity,
  useMergeEntity,
  useEntities,
} from "../api/hooks";

const TYPE_COLORS: Record<string, string> = {
  service: "#6c8cff",
  database: "#34d399",
  team: "#f59e42",
  api: "#f472b6",
  policy: "#a78bfa",
  person: "#fbbf24",
  document: "#60a5fa",
  capability: "#f87171",
  domain: "#2dd4bf",
  repository: "#c084fc",
  schema: "#fb923c",
  process: "#38bdf8",
};

const OBS_TYPE_COLORS: Record<string, string> = {
  entity: "bg-blue-100 text-blue-700",
  relationship: "bg-green-100 text-green-700",
  insight: "bg-amber-100 text-amber-700",
  contradiction: "bg-pink-100 text-pink-700",
  gap: "bg-purple-100 text-purple-700",
  decision: "bg-yellow-100 text-yellow-700",
  alignment: "bg-sky-100 text-sky-700",
};

interface Props {
  engagementId: string;
  entityId: string;
  onClose: () => void;
}

export default function EntityDetailPanel({
  engagementId,
  entityId,
  onClose,
}: Props) {
  const { data, isLoading } = useEntityDetail(engagementId, entityId);
  const { data: annotations } = useAnnotations(engagementId);
  const createAnnotation = useCreateAnnotation();
  const deleteAnnotation = useDeleteAnnotation();
  const updateEntity = useUpdateEntity();
  const mergeEntity = useMergeEntity();
  const { data: allEntities } = useEntities(engagementId, 0, 200);

  const [noteText, setNoteText] = useState("");
  const [showNote, setShowNote] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameValue, setNameValue] = useState("");
  const [editingType, setEditingType] = useState(false);
  const [typeValue, setTypeValue] = useState("");
  const [showMerge, setShowMerge] = useState(false);
  const [mergeSearch, setMergeSearch] = useState("");

  const entityAnnotations = annotations?.filter(
    (a) => a.entity_id === entityId,
  );

  const handleAnnotate = (type: string) => {
    createAnnotation.mutate({
      engagementId,
      data: { entity_id: entityId, annotation_type: type },
    });
  };

  const handleAddNote = () => {
    if (!noteText.trim()) return;
    createAnnotation.mutate(
      {
        engagementId,
        data: {
          entity_id: entityId,
          annotation_type: "note",
          content: noteText.trim(),
        },
      },
      {
        onSuccess: () => {
          setNoteText("");
          setShowNote(false);
        },
      },
    );
  };

  const handleSaveName = () => {
    if (nameValue.trim() && nameValue !== data?.name) {
      updateEntity.mutate({
        engagementId,
        entityId,
        data: { name: nameValue.trim() },
      });
    }
    setEditingName(false);
  };

  const handleSaveType = () => {
    if (typeValue.trim() && typeValue !== data?.entity_type) {
      updateEntity.mutate({
        engagementId,
        entityId,
        data: { entity_type: typeValue.trim() },
      });
    }
    setEditingType(false);
  };

  const mergeTargets = allEntities?.items?.filter(
    (e) =>
      e.entity_id !== entityId &&
      e.name.toLowerCase().includes(mergeSearch.toLowerCase()),
  );

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-black/30"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
    <div className="relative mx-4 max-h-[85vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-gray-200 bg-white p-5 shadow-xl">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-bold text-gray-900">Entity Detail</h3>
        <button
          onClick={onClose}
          className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {isLoading && (
        <p className="text-xs text-gray-400">Loading...</p>
      )}

      {data && (
        <div className="space-y-4">
          {/* Header */}
          <div>
            <div className="flex items-center gap-2">
              <span
                className="h-3 w-3 rounded-full"
                style={{
                  backgroundColor:
                    TYPE_COLORS[data.entity_type] ?? "#94a3b8",
                }}
              />
              {editingName ? (
                <input
                  value={nameValue}
                  onChange={(e) => setNameValue(e.target.value)}
                  onBlur={handleSaveName}
                  onKeyDown={(e) => e.key === "Enter" && handleSaveName()}
                  className="text-base font-medium text-gray-900 border-b border-indigo-300 outline-none bg-transparent"
                  autoFocus
                />
              ) : (
                <span
                  className="text-base font-medium text-gray-900 cursor-pointer hover:text-indigo-600"
                  onClick={() => {
                    setNameValue(data.name);
                    setEditingName(true);
                  }}
                  title="Click to rename"
                >
                  {data.name}
                </span>
              )}
            </div>
            <div className="mt-1 flex gap-2 text-xs text-gray-500">
              {editingType ? (
                <input
                  value={typeValue}
                  onChange={(e) => setTypeValue(e.target.value)}
                  onBlur={handleSaveType}
                  onKeyDown={(e) => e.key === "Enter" && handleSaveType()}
                  className="rounded bg-gray-100 px-1.5 py-0.5 border-b border-indigo-300 outline-none text-xs"
                  autoFocus
                />
              ) : (
                <span
                  className="rounded bg-gray-100 px-1.5 py-0.5 cursor-pointer hover:bg-indigo-100"
                  onClick={() => {
                    setTypeValue(data.entity_type);
                    setEditingType(true);
                  }}
                  title="Click to reclassify"
                >
                  {data.entity_type}
                </span>
              )}
              <span>{data.observation_count} observations</span>
            </div>
            {data.aliases.length > 0 && (
              <div className="mt-1 text-xs text-gray-400">
                Aliases: {data.aliases.join(", ")}
              </div>
            )}
          </div>

          {/* Actions */}
          <div>
            <h4 className="mb-1 text-xs font-medium text-gray-600">
              Actions
            </h4>
            <div className="flex flex-wrap gap-1">
              <button
                onClick={() => handleAnnotate("important")}
                className="rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700 hover:bg-amber-100"
              >
                Mark Important
              </button>
              <button
                onClick={() => handleAnnotate("explore_more")}
                className="rounded border border-indigo-200 bg-indigo-50 px-1.5 py-0.5 text-[10px] text-indigo-700 hover:bg-indigo-100"
              >
                Explore More
              </button>
              <button
                onClick={() => handleAnnotate("dismiss")}
                className="rounded border border-gray-200 bg-gray-50 px-1.5 py-0.5 text-[10px] text-gray-600 hover:bg-gray-100"
              >
                Dismiss
              </button>
              <button
                onClick={() => setShowNote(!showNote)}
                className="rounded border border-blue-200 bg-blue-50 px-1.5 py-0.5 text-[10px] text-blue-700 hover:bg-blue-100"
              >
                Add Note
              </button>
              <button
                onClick={() => setShowMerge(!showMerge)}
                className="rounded border border-purple-200 bg-purple-50 px-1.5 py-0.5 text-[10px] text-purple-700 hover:bg-purple-100"
              >
                Merge Into...
              </button>
            </div>
            {showNote && (
              <div className="mt-2 flex gap-1">
                <input
                  value={noteText}
                  onChange={(e) => setNoteText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddNote()}
                  placeholder="Add a note..."
                  className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs focus:border-indigo-300 focus:outline-none"
                  autoFocus
                />
                <button
                  onClick={handleAddNote}
                  className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700"
                >
                  Save
                </button>
              </div>
            )}
            {showMerge && (
              <div className="mt-2 space-y-1">
                <input
                  value={mergeSearch}
                  onChange={(e) => setMergeSearch(e.target.value)}
                  placeholder="Search entity to merge into..."
                  className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:border-indigo-300 focus:outline-none"
                  autoFocus
                />
                <div className="max-h-24 overflow-y-auto space-y-0.5">
                  {mergeTargets?.slice(0, 10).map((e) => (
                    <button
                      key={e.entity_id}
                      onClick={() => {
                        if (
                          confirm(
                            `Merge "${data.name}" into "${e.name}"? This cannot be undone.`,
                          )
                        ) {
                          mergeEntity.mutate({
                            engagementId,
                            targetEntityId: e.entity_id,
                            sourceEntityId: entityId,
                          });
                          setShowMerge(false);
                          onClose();
                        }
                      }}
                      className="block w-full text-left rounded px-2 py-1 text-xs text-gray-700 hover:bg-indigo-50"
                    >
                      {e.name}{" "}
                      <span className="text-gray-400">({e.entity_type})</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Annotations */}
          {entityAnnotations && entityAnnotations.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-medium text-gray-600">
                Annotations
              </h4>
              <div className="space-y-1 max-h-24 overflow-y-auto">
                {entityAnnotations.map((a) => (
                  <div
                    key={a.annotation_id}
                    className="flex items-center gap-1 text-xs"
                  >
                    <span className="rounded bg-gray-100 px-1 py-0.5 text-[10px] font-medium text-gray-600">
                      {a.annotation_type}
                    </span>
                    {a.content && (
                      <span className="text-gray-600 truncate">
                        {a.content}
                      </span>
                    )}
                    <button
                      onClick={() =>
                        deleteAnnotation.mutate({
                          engagementId,
                          annotationId: a.annotation_id,
                        })
                      }
                      className="ml-auto text-[10px] text-red-400 hover:text-red-600"
                    >
                      x
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Properties */}
          {Object.keys(data.properties).length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-medium text-gray-600">
                Properties
              </h4>
              <div className="space-y-1">
                {Object.entries(data.properties).map(([k, v]) => (
                  <div key={k} className="flex gap-2 text-xs">
                    <span className="text-gray-500">{k}:</span>
                    <span className="text-gray-700">{String(v)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Consolidated summary */}
          {data.consolidated_summary && (
            <div>
              <h4 className="mb-1 text-xs font-medium text-gray-600">
                Summary
              </h4>
              <p className="text-xs text-gray-700 whitespace-pre-line rounded bg-indigo-50 p-2">
                {data.consolidated_summary}
              </p>
            </div>
          )}

          {/* Relationships */}
          {(data.relationships_outgoing.length > 0 ||
            data.relationships_incoming.length > 0) && (
            <div>
              <h4 className="mb-1 text-xs font-medium text-gray-600">
                Relationships
              </h4>
              <div className="space-y-1 max-h-40 overflow-y-auto">
                {data.relationships_outgoing.map((r) => (
                  <div
                    key={r.relationship_id}
                    className="text-xs text-gray-600"
                  >
                    <span className="text-gray-400">-&gt;</span>{" "}
                    <span className="font-medium">{r.entity_name}</span>{" "}
                    <span className="text-gray-400">
                      ({r.relationship_type}, {(r.confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                ))}
                {data.relationships_incoming.map((r) => (
                  <div
                    key={r.relationship_id}
                    className="text-xs text-gray-600"
                  >
                    <span className="text-gray-400">&lt;-</span>{" "}
                    <span className="font-medium">{r.entity_name}</span>{" "}
                    <span className="text-gray-400">
                      ({r.relationship_type}, {(r.confidence * 100).toFixed(0)}%)
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Observations */}
          {data.observations.length > 0 && (
            <div>
              <h4 className="mb-1 text-xs font-medium text-gray-600">
                Observations ({data.observations.length})
              </h4>
              <div className="space-y-2 max-h-60 overflow-y-auto">
                {data.observations.map((o) => (
                  <div
                    key={o.observation_id}
                    className="rounded border border-gray-100 p-2"
                  >
                    <div className="flex items-center gap-1 mb-1">
                      <span
                        className={`rounded px-1 py-0.5 text-[10px] font-medium ${
                          OBS_TYPE_COLORS[o.observation_type] ??
                          "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {o.observation_type}
                      </span>
                      <span className="text-[10px] text-gray-400 truncate">
                        {o.source_ref}
                      </span>
                    </div>
                    <p className="text-xs text-gray-700 line-clamp-3">
                      {o.raw_text}
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timestamps */}
          <div className="text-[10px] text-gray-400 space-y-0.5">
            {data.first_seen && (
              <div>First seen: {new Date(data.first_seen).toLocaleString()}</div>
            )}
            {data.last_referenced && (
              <div>
                Last referenced: {new Date(data.last_referenced).toLocaleString()}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
    </div>
  );
}
