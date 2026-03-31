import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import { useGraph } from "../api/hooks";
import type { GraphNode, GraphEdge } from "../api/types";
import EntityDetailPanel from "./EntityDetailPanel";

// Extended palette — 20 distinct colors so dynamic types get good coverage
const TYPE_PALETTE = [
  "#6c8cff", "#34d399", "#f59e42", "#f472b6", "#a78bfa",
  "#fbbf24", "#60a5fa", "#f87171", "#2dd4bf", "#c084fc",
  "#fb923c", "#38bdf8", "#e879f9", "#4ade80", "#f97316",
  "#22d3ee", "#a3e635", "#f43f5e", "#818cf8", "#14b8a6",
];

// Tableau10 palette for community coloring
const COMMUNITY_COLORS = [
  "#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f",
  "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
];

const DEFAULT_COLOR = "#94a3b8";

// Dynamically assign colors to entity types based on the types present in the data
const typeColorCache = new Map<string, string>();
function colorForType(entityType: string): string {
  const cached = typeColorCache.get(entityType);
  if (cached) return cached;
  const color = TYPE_PALETTE[typeColorCache.size % TYPE_PALETTE.length];
  typeColorCache.set(entityType, color);
  return color;
}

/** Call once per render with all types to ensure stable ordering by frequency. */
function assignTypeColors(types: string[]): void {
  typeColorCache.clear();
  for (const t of types) {
    typeColorCache.set(t, TYPE_PALETTE[typeColorCache.size % TYPE_PALETTE.length]);
  }
}

type ColorMode = "community" | "type";

function nodeRadius(observationCount: number): number {
  return Math.max(6, Math.min(24, 4 + Math.sqrt(observationCount) * 3));
}

function colorForCommunity(communityId: number | null): string {
  if (communityId == null) return DEFAULT_COLOR;
  return COMMUNITY_COLORS[communityId % COMMUNITY_COLORS.length];
}

interface SimNode extends d3.SimulationNodeDatum {
  id: string;
  name: string;
  entity_type: string;
  observation_count: number;
  community_id: number | null;
  is_hub: boolean;
  is_bridge: boolean;
}

interface SimLink extends d3.SimulationLinkDatum<SimNode> {
  relationship_type: string;
  confidence: number;
}

function D3Graph({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  colorMode,
}: {
  nodes: GraphNode[];
  edges: GraphEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  colorMode: ColorMode;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const zoomRef = useRef<d3.ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const zoomScaleRef = useRef(1);
  const hoveredRef = useRef<string | null>(null);
  const positionCache = useRef<Map<string, { x: number; y: number }>>(
    new Map(),
  );
  const prevNodeIds = useRef<Set<string>>(new Set());
  const selectedRef = useRef(selectedNodeId);
  selectedRef.current = selectedNodeId;
  const colorModeRef = useRef(colorMode);
  colorModeRef.current = colorMode;

  const nodeColorFn = useCallback(
    (d: SimNode) =>
      colorModeRef.current === "community"
        ? colorForCommunity(d.community_id)
        : colorForType(d.entity_type),
    [],
  );

  // Main simulation effect
  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const svg = d3.select(svgRef.current);
    svg.selectAll("*").remove();

    const width = svgRef.current.clientWidth;
    const height = svgRef.current.clientHeight;

    // Determine topology changes
    const currentNodeIds = new Set(nodes.map((n) => n.id));
    const added = [...currentNodeIds].filter(
      (id) => !prevNodeIds.current.has(id),
    );
    const removed = [...prevNodeIds.current].filter(
      (id) => !currentNodeIds.has(id),
    );
    const topologyChanged = added.length > 0 || removed.length > 0;

    for (const id of removed) {
      positionCache.current.delete(id);
    }
    prevNodeIds.current = currentNodeIds;

    const simNodes: SimNode[] = nodes.map((n) => {
      const cached = positionCache.current.get(n.id);
      if (cached) {
        return { ...n, x: cached.x, y: cached.y };
      }
      return {
        ...n,
        x: width / 2 + (Math.random() - 0.5) * 100,
        y: height / 2 + (Math.random() - 0.5) * 100,
      };
    });
    const nodeMap = new Map(simNodes.map((n) => [n.id, n]));
    const simLinks: SimLink[] = edges
      .filter((e) => nodeMap.has(e.source) && nodeMap.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        relationship_type: e.relationship_type,
        confidence: e.confidence,
      }));

    // Max observation count for label threshold
    const maxObs = Math.max(...simNodes.map((n) => n.observation_count), 1);

    // Force parameter scaling — use edge density, not just node count
    const nodeCount = simNodes.length;
    const edgeDensity = simLinks.length / Math.max(nodeCount, 1);
    let linkDist: number;
    let chargeStrength: number;
    if (nodeCount > 150 || edgeDensity > 3) {
      linkDist = 180;
      chargeStrength = -600;
    } else if (nodeCount > 50 || edgeDensity > 2) {
      linkDist = 150;
      chargeStrength = -450;
    } else {
      linkDist = 100;
      chargeStrength = -300;
    }

    // Arrow marker
    const defs = svg.append("defs");
    defs
      .append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 20)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "#94a3b8");

    const initialAlpha = topologyChanged ? 0.3 : 0.05;
    const hasCache = positionCache.current.size > 0;

    const simulation = d3
      .forceSimulation<SimNode>(simNodes)
      .alpha(hasCache ? initialAlpha : 1)
      .force(
        "link",
        d3
          .forceLink<SimNode, SimLink>(simLinks)
          .id((d) => d.id)
          .distance(linkDist),
      )
      .force("charge", d3.forceManyBody().strength(chargeStrength))
      .force("center", d3.forceCenter(width / 2, height / 2))
      .force(
        "collision",
        d3.forceCollide<SimNode>().radius((d) => nodeRadius(d.observation_count) + 4),
      );

    const g = svg.append("g");

    // Zoom — track scale for label culling
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 6])
      .on("zoom", (event) => {
        g.attr("transform", event.transform);
        const k = event.transform.k as number;
        zoomScaleRef.current = k;
        updateLabelVisibility(labels, simNodes, maxObs, k);
      });
    svg.call(zoom);
    zoomRef.current = zoom;

    // Links — confidence-based opacity and width (relative to dataset range)
    const confValues = simLinks.map((l) => l.confidence);
    const confMin = Math.min(...confValues, 0);
    const confMax = Math.max(...confValues, 1);
    const confRange = confMax - confMin || 1;
    const normalizeConf = (c: number) => (c - confMin) / confRange; // 0..1

    const link = g
      .selectAll<SVGLineElement, SimLink>("line")
      .data(simLinks)
      .enter()
      .append("line")
      .attr("stroke", "#cbd5e1")
      .attr("stroke-opacity", (d) => 0.08 + normalizeConf(d.confidence) * 0.5)
      .attr("stroke-width", (d) => 0.3 + normalizeConf(d.confidence) * 1.7)
      .attr("marker-end", "url(#arrowhead)");

    // Link hover labels
    const linkLabel = g
      .selectAll<SVGTextElement, SimLink>(".link-label")
      .data(simLinks)
      .enter()
      .append("text")
      .attr("class", "link-label")
      .text((d) => d.relationship_type)
      .attr("font-size", "8px")
      .attr("fill", "#94a3b8")
      .attr("text-anchor", "middle")
      .attr("opacity", 0)
      .attr("pointer-events", "none");

    link
      .on("mouseenter", function (_event, d) {
        const idx = simLinks.indexOf(d);
        d3.select(linkLabel.nodes()[idx]).attr("opacity", 1);
        d3.select(this).attr("stroke", "#64748b").attr("stroke-width", 2);
      })
      .on("mouseleave", function (_event, d) {
        const idx = simLinks.indexOf(d);
        d3.select(linkLabel.nodes()[idx]).attr("opacity", 0);
        d3.select(this)
          .attr("stroke", "#cbd5e1")
          .attr("stroke-width", 0.3 + normalizeConf(d.confidence) * 1.7);
      });

    // Nodes — with hub/bridge border styles
    const nodeSelection = g
      .selectAll<SVGCircleElement, SimNode>("circle")
      .data(simNodes)
      .enter()
      .append("circle")
      .attr("r", (d) => nodeRadius(d.observation_count))
      .attr("fill", nodeColorFn)
      .attr("stroke", (d) => (d.is_hub ? "#1e293b" : "#fff"))
      .attr("stroke-width", (d) => (d.is_hub ? 2.5 : 1.5))
      .attr("stroke-dasharray", (d) => (d.is_bridge ? "3,2" : "none"))
      .attr("cursor", "pointer")
      .on("click", (_event, d) => {
        onSelectNode(d.id === selectedRef.current ? null : d.id);
      })
      .on("mouseenter", (_event, d) => {
        hoveredRef.current = d.id;
        updateLabelVisibility(labels, simNodes, maxObs, zoomScaleRef.current);
      })
      .on("mouseleave", () => {
        hoveredRef.current = null;
        updateLabelVisibility(labels, simNodes, maxObs, zoomScaleRef.current);
      })
      .call(
        d3
          .drag<SVGCircleElement, SimNode>()
          .on("start", (event, d) => {
            if (!event.active) simulation.alphaTarget(0.3).restart();
            d.fx = d.x;
            d.fy = d.y;
          })
          .on("drag", (event, d) => {
            d.fx = event.x;
            d.fy = event.y;
          })
          .on("end", (event, d) => {
            if (!event.active) simulation.alphaTarget(0);
            d.fx = null;
            d.fy = null;
          }),
      );

    // Labels — initially hidden, controlled by zoom-adaptive culling
    const labels = g
      .selectAll<SVGTextElement, SimNode>("text.node-label")
      .data(simNodes)
      .enter()
      .append("text")
      .attr("class", "node-label")
      .text((d) => d.name)
      .attr("font-size", "10px")
      .attr("dx", (d) => nodeRadius(d.observation_count) + 4)
      .attr("dy", 4)
      .attr("fill", "#374151")
      .attr("pointer-events", "none")
      .attr("opacity", 0);

    // Helper to update label visibility based on zoom.
    // At k=1, show top ~25 labels. As user zooms in, reveal more.
    function updateLabelVisibility(
      labelSel: d3.Selection<SVGTextElement, SimNode, SVGGElement, unknown>,
      allNodes: SimNode[],
      _maxObsCount: number,
      k: number,
    ) {
      const sortedObs = allNodes
        .map((n) => n.observation_count)
        .sort((a, b) => b - a);
      const targetVisible = Math.min(Math.floor(25 * k), allNodes.length);
      const threshold = targetVisible > 0 && targetVisible <= sortedObs.length
        ? sortedObs[targetVisible - 1]
        : 0;

      labelSel.attr("opacity", (d) => {
        if (d.id === selectedRef.current) return 1;
        if (d.id === hoveredRef.current) return 1;
        if (d.observation_count >= threshold) return 1;
        return 0;
      });
    }

    // Initial label visibility
    updateLabelVisibility(labels, simNodes, maxObs, zoomScaleRef.current);

    simulation.on("tick", () => {
      link
        .attr("x1", (d) => (d.source as SimNode).x!)
        .attr("y1", (d) => (d.source as SimNode).y!)
        .attr("x2", (d) => (d.target as SimNode).x!)
        .attr("y2", (d) => (d.target as SimNode).y!);

      linkLabel
        .attr(
          "x",
          (d) =>
            ((d.source as SimNode).x! + (d.target as SimNode).x!) / 2,
        )
        .attr(
          "y",
          (d) =>
            ((d.source as SimNode).y! + (d.target as SimNode).y!) / 2 - 4,
        );

      nodeSelection.attr("cx", (d) => d.x!).attr("cy", (d) => d.y!);
      labels.attr("x", (d) => d.x!).attr("y", (d) => d.y!);

      for (const n of simNodes) {
        if (n.x != null && n.y != null) {
          positionCache.current.set(n.id, { x: n.x, y: n.y });
        }
      }
    });

    return () => {
      simulation.stop();
    };
  }, [nodes, edges, onSelectNode, nodeColorFn]);

  // Color mode update — recolor without rebuilding graph
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll<SVGCircleElement, SimNode>("circle").attr("fill", nodeColorFn);
  }, [colorMode, nodeColorFn]);

  // Selection highlight
  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    svg.selectAll<SVGCircleElement, SimNode>("circle")
      .attr("stroke", (d) => {
        if (d.id === selectedNodeId) return "#1e293b";
        if (d.is_hub) return "#1e293b";
        return "#fff";
      })
      .attr("stroke-width", (d) => {
        if (d.id === selectedNodeId) return 3;
        if (d.is_hub) return 2.5;
        return 1.5;
      });
  }, [selectedNodeId]);

  const handleZoomToFit = useCallback(() => {
    if (!svgRef.current || !zoomRef.current) return;
    const svg = d3.select(svgRef.current);
    const gNode = svg.select("g").node() as SVGGElement | null;
    if (!gNode) return;

    const bounds = gNode.getBBox();
    if (bounds.width === 0 || bounds.height === 0) return;

    const fullWidth = svgRef.current.clientWidth;
    const fullHeight = svgRef.current.clientHeight;
    const padding = 40;

    const scale = Math.min(
      (fullWidth - padding * 2) / bounds.width,
      (fullHeight - padding * 2) / bounds.height,
      2,
    );
    const tx =
      fullWidth / 2 - (bounds.x + bounds.width / 2) * scale;
    const ty =
      fullHeight / 2 - (bounds.y + bounds.height / 2) * scale;

    svg
      .transition()
      .duration(500)
      .call(
        zoomRef.current.transform,
        d3.zoomIdentity.translate(tx, ty).scale(scale),
      );
  }, []);

  return (
    <div className="relative">
      <button
        onClick={handleZoomToFit}
        className="absolute right-2 top-2 z-10 rounded bg-white px-2 py-1 text-xs text-gray-600 shadow border border-gray-200 hover:bg-gray-50"
      >
        Fit
      </button>
      <svg
        ref={svgRef}
        className="h-[500px] w-full rounded-lg border border-gray-200 bg-white"
      />
    </div>
  );
}

function Legend({
  types,
  communityIds,
  colorMode,
}: {
  types: string[];
  communityIds: number[];
  colorMode: ColorMode;
}) {
  if (colorMode === "community" && communityIds.length > 0) {
    return (
      <div className="flex flex-wrap gap-3 px-1 py-2">
        {communityIds.map((c) => (
          <div key={c} className="flex items-center gap-1.5">
            <span
              className="inline-block h-3 w-3 rounded-full"
              style={{ backgroundColor: colorForCommunity(c) }}
            />
            <span className="text-xs text-gray-600">Cluster {c}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-3 border-l pl-3 border-gray-200">
          <span className="inline-block h-3 w-3 rounded-full border-2 border-gray-800 bg-transparent" />
          <span className="text-xs text-gray-600">Hub</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-3 rounded-full border-2 border-dashed border-gray-500 bg-transparent"
          />
          <span className="text-xs text-gray-600">Bridge</span>
        </div>
      </div>
    );
  }
  if (types.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-3 px-1 py-2">
      {types.map((t) => (
        <div key={t} className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-3 rounded-full"
            style={{ backgroundColor: colorForType(t) }}
          />
          <span className="text-xs text-gray-600">{t}</span>
        </div>
      ))}
    </div>
  );
}

/** Compute a smart min_observations default so ~40 nodes show on first load. */
function computeSmartMinObs(nodes: GraphNode[]): number {
  if (nodes.length <= 40) return 0;
  const sorted = nodes
    .map((n) => n.observation_count)
    .sort((a, b) => b - a);
  const target = 40;
  if (sorted.length <= target) return 0;
  return sorted[target - 1];
}

interface Props {
  engagementId: string;
  selectedEntityId?: string | null;
  onSelectEntity?: (id: string | null) => void;
}

export default function KnowledgeGraph({
  engagementId,
  selectedEntityId,
  onSelectEntity,
}: Props) {
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set());
  const [minObs, setMinObs] = useState<number | null>(null);
  const [smartDefaultApplied, setSmartDefaultApplied] = useState(false);
  const [localSelected, setLocalSelected] = useState<string | null>(null);
  const [colorMode, setColorMode] = useState<ColorMode>("type");

  const selected = selectedEntityId ?? localSelected;
  const setSelected = onSelectEntity ?? setLocalSelected;

  const entityTypesParam =
    typeFilters.size > 0 ? Array.from(typeFilters).join(",") : undefined;

  // Fetch with minObs=0 for smart default calculation, then use actual minObs
  const { data: fullData, isLoading } = useGraph(
    engagementId,
    entityTypesParam,
    minObs ?? 0,
  );

  // Apply smart default on first load
  useEffect(() => {
    if (fullData && minObs === null && !smartDefaultApplied) {
      const smart = computeSmartMinObs(fullData.nodes);
      setMinObs(smart);
      if (smart > 0) {
        setSmartDefaultApplied(true);
      }
    }
  }, [fullData, minObs, smartDefaultApplied]);

  if (isLoading) return <p className="text-sm text-gray-500">Loading...</p>;
  if (!fullData) return null;

  const effectiveMinObs = minObs ?? 0;

  // Count types by frequency so the most common types get the first palette colors
  const typeCounts = new Map<string, number>();
  for (const n of fullData.nodes) {
    typeCounts.set(n.entity_type, (typeCounts.get(n.entity_type) ?? 0) + 1);
  }
  const allTypes = Array.from(typeCounts.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([t]) => t);

  // Assign stable colors based on frequency order
  assignTypeColors(allTypes);

  const hasCommunities = fullData.nodes.some((n) => n.community_id != null);

  // If no community data, fall back to type coloring
  const effectiveColorMode = hasCommunities ? colorMode : "type";

  const communityIds = Array.from(
    new Set(
      fullData.nodes
        .map((n) => n.community_id)
        .filter((c): c is number => c != null),
    ),
  ).sort((a, b) => a - b);

  const maxObsCount = Math.max(
    ...fullData.nodes.map((n) => n.observation_count),
    1,
  );
  const sliderMax = Math.min(50, maxObsCount);

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-2 text-sm font-medium text-gray-700">
        Knowledge Graph
      </h3>

      {/* Filter controls */}
      <div className="mb-2 flex flex-wrap items-center gap-3">
        <div className="flex flex-wrap gap-1">
          {allTypes.map((t) => {
            const active =
              typeFilters.size === 0 || typeFilters.has(t);
            return (
              <button
                key={t}
                onClick={() => {
                  setTypeFilters((prev) => {
                    const next = new Set(prev);
                    if (next.has(t)) {
                      next.delete(t);
                    } else {
                      next.add(t);
                    }
                    return next;
                  });
                }}
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium border transition-colors ${
                  active
                    ? "border-gray-300 text-gray-700 bg-gray-50"
                    : "border-gray-200 text-gray-400 bg-white"
                }`}
                style={
                  active
                    ? { borderColor: colorForType(t), color: colorForType(t) }
                    : undefined
                }
              >
                {t}
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-1 text-xs text-gray-500">
          <label htmlFor="minObs">Min obs:</label>
          <input
            id="minObs"
            type="range"
            min={0}
            max={sliderMax}
            value={effectiveMinObs}
            onChange={(e) => {
              setMinObs(Number(e.target.value));
              setSmartDefaultApplied(false);
            }}
            className="h-1 w-20 accent-indigo-500"
          />
          <span className="w-6 text-center">{effectiveMinObs}</span>
        </div>
        {hasCommunities && (
          <button
            onClick={() =>
              setColorMode((m) => (m === "community" ? "type" : "community"))
            }
            className="rounded border border-gray-200 px-2 py-0.5 text-[10px] font-medium text-gray-600 hover:bg-gray-50"
          >
            Color: {effectiveColorMode === "community" ? "Community" : "Type"}
          </button>
        )}
        {(typeFilters.size > 0 || effectiveMinObs > 0) && (
          <button
            onClick={() => {
              setTypeFilters(new Set());
              setMinObs(0);
              setSmartDefaultApplied(false);
            }}
            className="text-[10px] text-indigo-500 hover:underline"
          >
            Reset
          </button>
        )}
      </div>

      {smartDefaultApplied && (
        <p className="mb-2 text-xs text-amber-600">
          Showing top entities. Adjust slider to see more.
        </p>
      )}

      <Legend
        types={allTypes}
        communityIds={communityIds}
        colorMode={effectiveColorMode}
      />

      {/* Graph */}
      {fullData.nodes.length > 0 ? (
        <div className="hidden md:block">
          <D3Graph
            nodes={fullData.nodes}
            edges={fullData.edges}
            selectedNodeId={selected}
            onSelectNode={setSelected}
            colorMode={effectiveColorMode}
          />
        </div>
      ) : (
        <p className="py-8 text-center text-sm text-gray-400">
          No entities match filters
        </p>
      )}

      {/* Mobile card list */}
      <div className="md:hidden space-y-2">
        {fullData.nodes.map((n) => (
          <button
            key={n.id}
            onClick={() => setSelected(n.id === selected ? null : n.id)}
            className={`w-full text-left rounded-md border px-3 py-2 ${
              n.id === selected
                ? "border-indigo-300 bg-indigo-50"
                : "border-gray-200 bg-white"
            }`}
          >
            <span className="text-sm font-medium text-gray-900">
              {n.name}
            </span>
            <span
              className="ml-2 inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: colorForType(n.entity_type) }}
            />
            <span className="ml-1 text-xs text-gray-500">
              {n.entity_type}
            </span>
          </button>
        ))}
        {fullData.nodes.length === 0 && (
          <p className="text-sm text-gray-400">No entities yet</p>
        )}
      </div>

      {/* Entity detail panel */}
      {selected && (
        <EntityDetailPanel
          engagementId={engagementId}
          entityId={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  );
}
