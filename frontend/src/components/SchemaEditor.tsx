import { useState } from "react";
import {
  useSchema,
  useTemplates,
  useApplyTemplate,
  useAddSchemaEntry,
  useProposeSchema,
} from "../api/hooks";

export default function SchemaEditor({
  engagementId,
}: {
  engagementId: string;
}) {
  const { data: schema, isLoading } = useSchema(engagementId);
  const { data: templates } = useTemplates();
  const applyTemplate = useApplyTemplate();
  const addEntry = useAddSchemaEntry();
  const proposeSchema = useProposeSchema();

  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [newKind, setNewKind] = useState<"entity_type" | "relationship_type">(
    "entity_type",
  );
  const [newName, setNewName] = useState("");
  const [showAdd, setShowAdd] = useState(false);
  const [proposal, setProposal] = useState<{
    reasoning: string;
    entity_types: Record<string, unknown>[];
    relationship_types: Record<string, unknown>[];
  } | null>(null);

  const entityTypes = schema?.filter((s) => s.kind === "entity_type") ?? [];
  const relTypes =
    schema?.filter((s) => s.kind === "relationship_type") ?? [];

  const handleApplyTemplate = () => {
    if (selectedTemplate) {
      applyTemplate.mutate({ engagementId, templateId: selectedTemplate });
    }
  };

  const handleAddEntry = () => {
    const trimmed = newName.trim().toLowerCase().replace(/\s+/g, "_");
    if (trimmed) {
      addEntry.mutate({
        engagementId,
        data: { kind: newKind, name: trimmed },
      });
      setNewName("");
      setShowAdd(false);
    }
  };

  const handlePropose = async () => {
    const result = await proposeSchema.mutateAsync(engagementId);
    setProposal(result);
  };

  const handleApplyProposal = () => {
    if (!proposal) return;
    for (const et of proposal.entity_types) {
      addEntry.mutate({
        engagementId,
        data: {
          kind: "entity_type",
          name: String(et.name || ""),
          description: String(et.description || ""),
          examples: Array.isArray(et.examples)
            ? et.examples.map(String)
            : [],
        },
      });
    }
    for (const rt of proposal.relationship_types) {
      addEntry.mutate({
        engagementId,
        data: {
          kind: "relationship_type",
          name: String(rt.name || ""),
          description: String(rt.description || ""),
          examples: Array.isArray(rt.examples)
            ? rt.examples.map(String)
            : [],
          parent_category: rt.parent_category
            ? String(rt.parent_category)
            : undefined,
        },
      });
    }
    setProposal(null);
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-gray-700">
          Ontology Schema
        </h3>
        <div className="flex gap-2">
          <button
            onClick={() => setShowAdd(!showAdd)}
            className="text-xs text-indigo-600 hover:text-indigo-800"
          >
            + Add Type
          </button>
          <button
            onClick={handlePropose}
            disabled={proposeSchema.isPending}
            className="text-xs text-indigo-600 hover:text-indigo-800 disabled:opacity-50"
          >
            {proposeSchema.isPending ? "Proposing..." : "Propose Schema"}
          </button>
        </div>
      </div>

      {/* Template selector */}
      {templates && templates.length > 0 && (
        <div className="flex gap-2 mb-3">
          <select
            value={selectedTemplate}
            onChange={(e) => setSelectedTemplate(e.target.value)}
            className="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
          >
            <option value="">Select template...</option>
            {templates.map((t) => (
              <option key={t.template_id} value={t.template_id}>
                {t.name} ({t.entity_type_count}E / {t.relationship_type_count}R)
              </option>
            ))}
          </select>
          <button
            onClick={handleApplyTemplate}
            disabled={!selectedTemplate || applyTemplate.isPending}
            className="text-xs bg-indigo-600 text-white px-3 py-1 rounded hover:bg-indigo-700 disabled:opacity-50"
          >
            Apply
          </button>
        </div>
      )}

      {/* Add type form */}
      {showAdd && (
        <div className="flex gap-2 mb-3">
          <select
            value={newKind}
            onChange={(e) =>
              setNewKind(
                e.target.value as "entity_type" | "relationship_type",
              )
            }
            className="text-xs border border-gray-300 rounded px-2 py-1"
          >
            <option value="entity_type">Entity</option>
            <option value="relationship_type">Relationship</option>
          </select>
          <input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleAddEntry()}
            placeholder="type_name"
            className="flex-1 text-xs border border-gray-300 rounded px-2 py-1"
          />
          <button
            onClick={handleAddEntry}
            disabled={!newName.trim()}
            className="text-xs bg-green-600 text-white px-3 py-1 rounded hover:bg-green-700 disabled:opacity-50"
          >
            Add
          </button>
        </div>
      )}

      {/* Proposal result */}
      {proposal && (
        <div className="mb-3 p-2 bg-blue-50 border border-blue-200 rounded text-xs">
          <div className="flex justify-between items-start mb-1">
            <span className="font-medium text-blue-800">
              Proposed: {proposal.entity_types.length} entity types,{" "}
              {proposal.relationship_types.length} relationship types
            </span>
            <div className="flex gap-1">
              <button
                onClick={handleApplyProposal}
                className="text-xs bg-blue-600 text-white px-2 py-0.5 rounded"
              >
                Apply All
              </button>
              <button
                onClick={() => setProposal(null)}
                className="text-xs text-gray-500 hover:text-gray-700"
              >
                Dismiss
              </button>
            </div>
          </div>
          {proposal.reasoning && (
            <p className="text-blue-700 mt-1">{proposal.reasoning}</p>
          )}
        </div>
      )}

      {/* Current types */}
      {isLoading ? (
        <p className="text-xs text-gray-400">Loading...</p>
      ) : (
        <div className="space-y-2">
          {entityTypes.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">
                Entity Types
              </p>
              <div className="flex flex-wrap gap-1">
                {entityTypes.map((t) => (
                  <span
                    key={t.schema_entry_id}
                    title={t.description}
                    className="inline-block text-xs bg-indigo-100 text-indigo-700 px-2 py-0.5 rounded"
                  >
                    {t.name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {relTypes.length > 0 && (
            <div>
              <p className="text-xs font-medium text-gray-500 mb-1">
                Relationship Types
              </p>
              <div className="flex flex-wrap gap-1">
                {relTypes.map((t) => (
                  <span
                    key={t.schema_entry_id}
                    title={t.description}
                    className="inline-block text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded"
                  >
                    {t.name}
                  </span>
                ))}
              </div>
            </div>
          )}
          {entityTypes.length === 0 && relTypes.length === 0 && (
            <p className="text-xs text-gray-400">
              No schema types defined. Apply a template to get started.
            </p>
          )}
        </div>
      )}
    </div>
  );
}
