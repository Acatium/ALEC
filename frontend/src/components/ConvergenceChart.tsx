import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { ConvergenceEntry } from "../api/types";

const THRESHOLD = 3.0;

export default function ConvergenceChart({
  data,
}: {
  data: ConvergenceEntry[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || data.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const margin = { top: 16, right: 16, bottom: 32, left: 40 };
    const width = svgRef.current.clientWidth - margin.left - margin.right;
    const height = 200 - margin.top - margin.bottom;

    const g = svg
      .append("g")
      .attr("transform", `translate(${margin.left},${margin.top})`);

    const x = d3
      .scaleLinear()
      .domain([
        d3.min(data, (d) => d.cycle_number) ?? 1,
        d3.max(data, (d) => d.cycle_number) ?? 1,
      ])
      .range([0, width]);

    const maxRatio = d3.max(data, (d) => d.weighted_ratio ?? 0) ?? 1;
    const y = d3
      .scaleLinear()
      .domain([0, Math.max(maxRatio * 1.1, THRESHOLD * 1.2)])
      .range([height, 0]);

    // Axes
    g.append("g")
      .attr("transform", `translate(0,${height})`)
      .call(d3.axisBottom(x).ticks(data.length).tickFormat(d3.format("d")))
      .selectAll("text")
      .attr("class", "text-xs fill-gray-500");

    g.append("g")
      .call(d3.axisLeft(y).ticks(5))
      .selectAll("text")
      .attr("class", "text-xs fill-gray-500");

    // Threshold line
    g.append("line")
      .attr("x1", 0)
      .attr("x2", width)
      .attr("y1", y(THRESHOLD))
      .attr("y2", y(THRESHOLD))
      .attr("stroke", "#f59e0b")
      .attr("stroke-dasharray", "4 4")
      .attr("stroke-width", 1.5);

    g.append("text")
      .attr("x", width - 4)
      .attr("y", y(THRESHOLD) - 4)
      .attr("text-anchor", "end")
      .attr("class", "text-[10px] fill-amber-500")
      .text("threshold");

    // Line
    const line = d3
      .line<ConvergenceEntry>()
      .x((d) => x(d.cycle_number))
      .y((d) => y(d.weighted_ratio ?? 0))
      .curve(d3.curveMonotoneX);

    g.append("path")
      .datum(data)
      .attr("fill", "none")
      .attr("stroke", "#6366f1")
      .attr("stroke-width", 2)
      .attr("d", line);

    // Dots
    g.selectAll("circle")
      .data(data)
      .enter()
      .append("circle")
      .attr("cx", (d) => x(d.cycle_number))
      .attr("cy", (d) => y(d.weighted_ratio ?? 0))
      .attr("r", 4)
      .attr("fill", "#6366f1")
      .attr("stroke", "#fff")
      .attr("stroke-width", 1.5);

    // Axis labels
    svg
      .append("text")
      .attr("x", margin.left + width / 2)
      .attr("y", margin.top + height + margin.bottom - 4)
      .attr("text-anchor", "middle")
      .attr("class", "text-xs fill-gray-400")
      .text("Cycle");
  }, [data]);

  if (data.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <h3 className="mb-2 text-sm font-medium text-gray-700">
          Convergence
        </h3>
        <p className="text-xs text-gray-400">No convergence data yet</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-medium text-gray-700">Convergence</h3>
      <svg ref={svgRef} className="h-[200px] w-full" />
    </div>
  );
}
