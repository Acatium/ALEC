export interface Engagement {
  engagement_id: string;
  name: string;
  status: string;
  entity_count: number;
  relationship_count: number;
  observation_count: number;
  problem_statement?: string;
  summary?: string;
  config?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface EngagementCreate {
  sources: string[];
  problem_statement?: string;
  max_cycles?: number;
  name?: string;
  summary?: string;
}

export interface Entity {
  entity_id: string;
  name: string;
  entity_type: string;
  observation_count: number;
  properties: Record<string, unknown>;
}

export interface Relationship {
  relationship_id: string;
  from_entity: string;
  to_entity: string;
  relationship_type: string;
  confidence: number;
}

export interface Observation {
  observation_id: string;
  source_ref: string;
  raw_text: string;
  observation_type: string;
  created_at: string;
}

export interface GraphNode {
  id: string;
  name: string;
  entity_type: string;
  observation_count: number;
  community_id: number | null;
  is_hub: boolean;
  is_bridge: boolean;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship_type: string;
  confidence: number;
  from_name?: string;
  to_name?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  offset: number;
  limit: number;
}

export interface ALECEvent {
  event_type: string;
  timestamp: string;
  engagement_id?: string;
  [key: string]: unknown;
}

export interface AnalyzeRequest {
  problem_statement: string;
  sources: string[];
}

export interface TopicCoverage {
  topic: string;
  description: string;
  covered_by: string[];
  coverage_level: "full" | "partial" | "none";
  importance: "critical" | "high" | "medium";
}

export interface SuggestedSource {
  url: string;
  title: string;
  reason: string;
  covers_topics: string[];
  reachable: boolean;
}

export interface AnalyzeResponse {
  topics: TopicCoverage[];
  gaps: string[];
  suggested_sources: SuggestedSource[];
  search_queries: string[];
  overall_assessment: string;
}

// --- Task / Timeline ---

export interface TaskItem {
  task_id: string;
  directive: string;
  source_type: string;
  source_ref: string;
  max_scope: string;
  status: string;
  assigned_worker?: string;
  result_summary?: Record<string, unknown>;
  created_at?: string;
  started_at?: string;
  completed_at?: string;
}

// --- Convergence ---

export interface ConvergenceEntry {
  cycle_number: number;
  reinforcement_count: number;
  expansion_count: number;
  challenge_count: number;
  ratio: number | null;
  weighted_ratio: number | null;
}

// --- Source Config ---

export interface SourceConfigEntry {
  source_type: string;
  config: Record<string, unknown>;
  status: string;
}

// --- Engagement Stats ---

export interface EngagementStats {
  entity_count: number;
  relationship_count: number;
  observation_count: number;
  task_count: number;
  cycle_count: number;
  entity_type_breakdown: Record<string, number>;
  observation_type_breakdown: Record<string, number>;
  task_status_breakdown: Record<string, number>;
  convergence_history: ConvergenceEntry[];
  source_configs: SourceConfigEntry[];
}

// --- Consolidated Units ---

export interface ConsolidatedUnit {
  unit_id: string;
  subject_entity_id?: string;
  subject_entity_name?: string;
  summary: string;
  token_count: number;
  version: number;
  freshness?: string;
  status: string;
}

// --- Source Config (full) ---

export interface SourceConfig {
  source_config_id: string;
  source_type: string;
  config: Record<string, unknown>;
  status: string;
  priority: number;
  trust_tier: string;
}

// --- Annotations ---

export interface Annotation {
  annotation_id: string;
  entity_id: string;
  annotation_type: string;
  content: string;
  created_at: string;
}

// --- Questions ---

export interface Question {
  question_id: string;
  question_text: string;
  status: string;
  answer: string | null;
  created_at: string;
  answered_at: string | null;
}

// --- Snapshots ---

export interface Snapshot {
  snapshot_id: string;
  name: string;
  description: string;
  entity_count: number;
  relationship_count: number;
  observation_count: number;
  cycle_count: number;
  convergence_ratio: number | null;
  created_at: string;
}

// --- Schema ---

export interface SchemaEntry {
  schema_entry_id: string;
  kind: "entity_type" | "relationship_type";
  name: string;
  description: string;
  examples: string[];
  parent_category: string | null;
  is_active: boolean;
}

export interface SchemaProposal {
  template_base: string;
  entity_types: Record<string, unknown>[];
  relationship_types: Record<string, unknown>[];
  reasoning: string;
}

export interface EngagementTemplate {
  template_id: string;
  name: string;
  description: string;
  entity_type_count: number;
  relationship_type_count: number;
}

// --- Report ---

export interface Report {
  markdown: string;
  title: string;
  generated_at: string;
}

// --- Entity Detail ---

export interface EntityObservation {
  observation_id: string;
  source_ref: string;
  raw_text: string;
  observation_type: string;
  created_at: string;
}

export interface EntityRelationship {
  relationship_id: string;
  entity_id: string;
  entity_name: string;
  relationship_type: string;
  confidence: number;
  direction: "outgoing" | "incoming";
}

export interface EntityDetail {
  entity_id: string;
  name: string;
  entity_type: string;
  aliases: string[];
  observation_count: number;
  properties: Record<string, unknown>;
  first_seen?: string;
  last_referenced?: string;
  observations: EntityObservation[];
  relationships_outgoing: EntityRelationship[];
  relationships_incoming: EntityRelationship[];
  consolidated_summary?: string;
}
