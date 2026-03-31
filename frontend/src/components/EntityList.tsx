import { useState } from "react";
import { useEntities } from "../api/hooks";

export default function EntityList({
  engagementId,
}: {
  engagementId: string;
}) {
  const [search, setSearch] = useState("");
  const { data, isLoading } = useEntities(engagementId, 0, 100);

  if (isLoading) return <p className="text-sm text-gray-500">Loading...</p>;
  if (!data) return null;

  const filtered = search
    ? data.items.filter(
        (e) =>
          e.name.toLowerCase().includes(search.toLowerCase()) ||
          e.entity_type.toLowerCase().includes(search.toLowerCase()),
      )
    : data.items;

  return (
    <div>
      <input
        type="text"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search entities..."
        className="mb-3 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
      />
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200 text-sm">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-4 py-2 text-left font-medium text-gray-500">
                Name
              </th>
              <th className="px-4 py-2 text-left font-medium text-gray-500">
                Type
              </th>
              <th className="px-4 py-2 text-right font-medium text-gray-500">
                Observations
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 bg-white">
            {filtered.map((ent) => (
              <tr key={ent.entity_id}>
                <td className="px-4 py-2 font-medium text-gray-900">
                  {ent.name}
                </td>
                <td className="px-4 py-2 text-gray-500">{ent.entity_type}</td>
                <td className="px-4 py-2 text-right text-gray-500">
                  {ent.observation_count}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && (
          <p className="py-4 text-center text-sm text-gray-400">
            No entities found
          </p>
        )}
      </div>
    </div>
  );
}
