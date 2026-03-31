import { useEffect, useRef } from "react";
import * as d3 from "d3";

const TYPE_COLORS: Record<string, string> = {
  entity: "#6c8cff",
  relationship: "#34d399",
  insight: "#f59e42",
  contradiction: "#f472b6",
  gap: "#a78bfa",
  decision: "#fbbf24",
  alignment: "#60a5fa",
};

export default function ObservationBreakdown({
  data,
}: {
  data: Record<string, number> | undefined;
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data || Object.keys(data).length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);
    const margin = { top: 8, right: 8, bottom: 8, left: 80 };
    const barHeight = 20;
    const gap = 4;
    const height =
      entries.length * (barHeight + gap) + margin.top + margin.bottom;
    const width = svgRef.current.clientWidth - margin.left - margin.right;

    svg.attr("height", height);

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3
      .scaleLinear()
      .domain([0, d3.max(entries, (d) => d[1]) ?? 1])
      .range([0, width]);

    entries.forEach(([type, count], i) => {
      const y = i * (barHeight + gap);
      const color = TYPE_COLORS[type] ?? "#94a3b8";

      g.append("rect")
        .attr("x", 0)
        .attr("y", y)
        .attr("width", x(count))
        .attr("height", barHeight)
        .attr("rx", 3)
        .attr("fill", color)
        .attr("opacity", 0.8);

      g.append("text")
        .attr("x", -4)
        .attr("y", y + barHeight / 2)
        .attr("text-anchor", "end")
        .attr("dominant-baseline", "central")
        .attr("class", "text-[11px] fill-gray-600")
        .text(type);

      g.append("text")
        .attr("x", x(count) + 4)
        .attr("y", y + barHeight / 2)
        .attr("dominant-baseline", "central")
        .attr("class", "text-[10px] fill-gray-500")
        .text(String(count));
    });
  }, [data]);

  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-700">
          Observations
        </h3>
        <p className="text-xs text-gray-400">No observations yet</p>
      </div>
    );
  }

  const entryCount = Object.keys(data).length;
  const svgHeight = entryCount * 24 + 16;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-medium text-gray-700">Observations</h3>
      <svg ref={svgRef} className="w-full" style={{ height: svgHeight }} />
    </div>
  );
}
