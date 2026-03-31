import { useState } from "react";
import { useCreateDirective } from "../api/hooks";

interface Props {
  engagementId: string;
}

export default function DirectiveCreator({ engagementId }: Props) {
  const createDirective = useCreateDirective();
  const [directive, setDirective] = useState("");
  const [sourceRef, setSourceRef] = useState("");
  const [scope, setScope] = useState("focused");
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = () => {
    if (!directive.trim()) return;
    createDirective.mutate(
      {
        engagementId,
        data: {
          directive: directive.trim(),
          source_ref: sourceRef.trim() || undefined,
          max_scope: scope,
        },
      },
      {
        onSuccess: () => {
          setDirective("");
          setSourceRef("");
          setSubmitted(true);
          setTimeout(() => setSubmitted(false), 3000);
        },
      },
    );
  };

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">
        Manual Directive
      </h3>

      <textarea
        value={directive}
        onChange={(e) => setDirective(e.target.value)}
        placeholder="Tell a worker what to explore..."
        rows={3}
        className="w-full rounded border border-gray-200 px-2 py-1.5 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-300 focus:outline-none"
      />

      <div className="mt-2 flex items-center gap-2">
        <input
          type="text"
          value={sourceRef}
          onChange={(e) => setSourceRef(e.target.value)}
          placeholder="Source (optional)"
          className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-300 focus:outline-none"
        />
        <select
          value={scope}
          onChange={(e) => setScope(e.target.value)}
          className="rounded border border-gray-200 px-1 py-1 text-xs text-gray-600"
        >
          <option value="survey">Survey</option>
          <option value="focused">Focused</option>
          <option value="deep">Deep</option>
        </select>
      </div>

      <div className="mt-2 flex items-center gap-2">
        <button
          onClick={handleSubmit}
          disabled={createDirective.isPending || !directive.trim()}
          className="rounded bg-indigo-600 px-3 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {createDirective.isPending ? "Sending..." : "Send Directive"}
        </button>
        {submitted && (
          <span className="text-xs text-green-600">
            Queued — will dispatch next cycle
          </span>
        )}
      </div>
    </div>
  );
}
