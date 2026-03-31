/**
 * API Types - Matching core/session/api/models.py exactly
 *
 * CRITICAL: These types must match the backend Pydantic models.
 * See: core/session/api/models.py
 */

// ============================================================================
// Token Usage
// ============================================================================

export interface TokenUsage {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cost_usd: number;
}

// ============================================================================
// Chat Types
// ============================================================================

export interface ChatRequest {
  session_id?: string;
  message: string;
  metadata?: Record<string, unknown>;
}

export interface ChatResponse {
  session_id: string;
  message: string;
  timestamp: string;
  tool_calls: Record<string, unknown>[];
  token_usage: TokenUsage | null;
  bullets_used: BulletUsed[];
}

export interface BulletUsed {
  id: string;
  situation: string;
  assertion: string;
  score?: number;
}

// ============================================================================
// Session Types
// ============================================================================

export interface SessionCreate {
  metadata?: Record<string, unknown>;
}

export interface SessionResponse {
  session_id: string;
  created_at: string;
  updated_at: string;
  status: string;
  message_count: number;
  token_usage: TokenUsage | null;
}

export interface SessionMicroOutcomes {
  solved: number;
  progress: number;
  stuck: number;
  error: number;
}

export interface SessionMetadata {
  session_id: string;
  user_id: string | null;
  title: string | null;
  domain: string;
  playbook_id: string | null;
  status: string;
  metadata: Record<string, unknown>;
  message_count: number;
  token_usage: TokenUsage | null;
  duration_ms: number | null;
  micro_outcomes: SessionMicroOutcomes | null;
  created_at: string;
  updated_at: string;
}

export interface SessionListResponse {
  sessions: SessionMetadata[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionCompleteRequest {
  status: 'completed' | 'failed';
  reason?: string;
}

export interface MessageResponse {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  metadata: Record<string, unknown>;
}

export interface SessionHistoryResponse {
  session_id: string;
  title: string | null;
  domain: string | null;
  status: string;
  message_count: number | null;
  created_at: string | null;
  updated_at: string | null;
  metadata: Record<string, unknown> | null;
  messages: MessageResponse[];
  total_messages: number;
  token_usage: TokenUsage | null;
}

export interface SessionBulletsResponse {
  session_id: string;
  bullets: BulletResponse[];
  total: number;
}

// ============================================================================
// Turn Types (v3 - First-class entities)
// ============================================================================

export type MicroOutcome = 'progress' | 'solved' | 'stuck' | 'error';

export interface Turn {
  turn_id: string;
  turn_number: number;
  user_message: string;
  assistant_response: string;
  sub_task: string | null;
  micro_outcome: MicroOutcome | null;
  error_trace: string | null;
  akus_shown: string[];
  akus_helped: string[];
  akus_harmed: string[];
  created_at: string;
}

export interface SessionWithTurns extends SessionMetadata {
  turns: Turn[];
}

export interface SessionTurnsResponse {
  session_id: string;
  turns: Turn[];
  micro_outcomes: SessionMicroOutcomes;
}

// ============================================================================
// AKU Types (v4 - Simplified)
// ============================================================================

export type BulletStatus = 'candidate' | 'active' | 'archived' | 'banned';

export interface BulletResponse {
  id: string;
  situation: string;
  assertion: string;
  helpful_count: number;
  harmful_count: number;
  neutral_count: number;
  status: BulletStatus;
  created_at: string;
}

export interface BulletUpdate {
  content?: string;
  status?: BulletStatus;
  category?: string;
}

export interface BulletListParams {
  page?: number;
  page_size?: number;
  sort_by?: 'created_at' | 'helpful_count' | 'harmful_count' | 'status';
  sort_order?: 'asc' | 'desc';
  status?: BulletStatus;
  category?: string;
  search?: string;
}

export interface BulletListResponse {
  bullets: BulletResponse[];
  total: number;
  page: number;
  page_size: number;
}

// ============================================================================
// Evaluation Types (v2 - Full functionality)
// ============================================================================

export interface ExperimentCreate {
  name: string;
  experiment_type: string; // baseline, learning_curve, bullet_evolution
  dataset_split: string; // train, dev, test_normal, test_challenge
  task_limit?: number;
  checkpoint_interval?: number;
  turns_per_task?: number;
  grouping_strategy?: string;
  specific_task_ids?: string[];
  comparison_group_id?: string;
}

// Response type for list endpoint (summary)
export interface ExperimentSummary {
  id: string;
  name: string;
  experiment_type: string;
  dataset_split: string;
  status: string;
  success_rate: number | null;
  avg_tokens: number | null;
  tasks_completed: number;
  tasks_total: number;
  created_at: string;
  completed_at: string | null;
  total_assertions: number;
  passed_assertions: number;
}

// Response type for single experiment (detail)
export interface ExperimentDetail {
  id: string;
  name: string;
  experiment_type: string;
  dataset_split: string;
  status: string;
  config: Record<string, unknown>;
  success_rate: number | null;
  avg_iterations: number | null;
  avg_tokens: number | null;
  tasks_completed: number;
  tasks_total: number;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  total_assertions: number;
  passed_assertions: number;
}

// For backwards compatibility
export type ExperimentResponse = ExperimentDetail;

export interface ExperimentListResponse {
  experiments: ExperimentSummary[];
  total: number;
}

export interface TestResultsSummary {
  passes: string[];
  failures: string[];
  num_tests: number;
}

export interface MicroOutcomes {
  solved: number;
  progress: number;
  stuck: number;
  error: number;
}

export interface TaskResultResponse {
  id: string;
  task_id: string;
  session_id: string | null;
  success: boolean;
  iterations: number;
  tokens_used: number | null;
  duration_ms: number | null;
  error_message: string | null;
  test_results: TestResultsSummary | null;
  task_description: string | null;
  micro_outcomes: MicroOutcomes | null;
  created_at: string;
}

export interface CheckpointResponse {
  checkpoint_number: number;
  tasks_completed: number;
  success_rate: number;
  avg_iterations: number | null;
  avg_tokens: number | null;
  bullet_count: number | null;
  created_at: string;
}

export interface ExperimentResults {
  experiment: ExperimentDetail;
  task_results: TaskResultResponse[];
  checkpoints: CheckpointResponse[];
  total_assertions: number;
  passed_assertions: number;
  assertion_pass_rate: number | null;
}

// For backwards compatibility with old interface
export interface ExperimentResultsResponse {
  experiment: ExperimentDetail;
  task_results: TaskResultResponse[];
  checkpoints: CheckpointResponse[];
  total_assertions: number;
  passed_assertions: number;
  assertion_pass_rate: number | null;
}

// EpochInfo matches Python core/session/api/evaluation/models.py
export interface EpochInfo {
  id: string;
  name: string;
  created_at: string;
  success_rate: number | null;
  avg_iterations: number | null;
  avg_tokens: number | null;
  tasks_completed: number;
}

export interface TaskTrajectory {
  task_id: string;
  task_description: string | null;
  results: (boolean | null)[];  // True=success, False=fail, null=not run
  first_success_epoch: number | null;
  pattern: string;  // "improved", "regressed", "consistent_success", "consistent_failure", "intermittent"
}

export interface BulletImpact {
  bullet_id: string;
  content: string;
  category: string;
  first_appeared_epoch: number;
  tasks_improved: number;
  tasks_regressed: number;
  net_impact: number;
}

// EpochsComparisonResponse matches Python core/session/api/evaluation/models.py
export interface EpochsComparisonResponse {
  epochs: EpochInfo[];
  task_trajectories: TaskTrajectory[];
  bullet_impact: BulletImpact[];
  summary: Record<string, unknown>;
}

// Legacy type for backwards compatibility
export interface EpochComparison {
  id: string;
  name: string;
  experiment_type: string;
  dataset_split: string;
  status: string;
  success_rate: number | null;
  tasks_completed: number;
  tasks_total: number;
  created_at: string;
  completed_at: string | null;
  total_assertions: number;
  passed_assertions: number;
}

// ============================================================================
// System Types
// ============================================================================

export interface HealthResponse {
  status: 'healthy' | 'degraded';
  postgres: string;
  redis: string;
  kafka: string;
}

export interface ResetTarget {
  target: 'all' | 'counters' | 'sessions' | 'evaluations' | 'redis' | 'bullets';
}

export interface TopBullet {
  id: string;
  content: string;
  helpful: number;
  harmful: number;
}

export interface RecentChange {
  id: string;
  content: string;
  status: string;
  updated_at: string;
}

export interface LearningStatsResponse {
  total_bullets: number;
  active_bullets: number;
  total_sessions: number;
  successful_sessions: number;
  avg_effectiveness: number;
  top_bullets: TopBullet[];
  recent_changes: RecentChange[];
}

// Alias for backwards compatibility
export type LearningStats = LearningStatsResponse;

export interface IntelligenceReport {
  knowledge_gaps: Array<{
    cluster_id: string;
    label: string;
    failures: number;
    successes: number;
  }>;
  struggling_clusters: Array<{
    cluster_id: string;
    label: string;
    turns: number;
    success_rate: number;
  }>;
  harmful_bullets: Array<{
    id: string;
    content: string;
    harmful: number;
    helpful: number;
  }>;
  recommendations?: string[];
  timestamp: string;
}

// ============================================================================
// Knowledge Graph Types
// ============================================================================

export interface ClusterResponse {
  cluster_id: string;
  label: string;
  description: string | null;
  turn_count: number;
  success_count: number;
  failure_count: number;
  status: string;
  solved_by_edges: number;
  caused_failure_edges: number;
  created_at: string;
  updated_at: string;
}

export interface ClusterListResponse {
  clusters: ClusterResponse[];
  total: number;
  page: number;
  page_size: number;
}

export interface EdgeResponse {
  edge_id: string;
  source_type: string;
  source_id: string;
  target_type: string;
  target_id: string;
  edge_type: string;
  weight: number;
  evidence_count: number;
  created_at: string;
}

export interface EdgeListResponse {
  edges: EdgeResponse[];
  total: number;
}

export interface GraphHealthResponse {
  total_clusters: number;
  active_clusters: number;
  total_edges: number;
  solved_by_edges: number;
  caused_failure_edges: number;
  avg_cluster_success_rate: number;
}

export interface LearningHealthResponse {
  status: 'healthy' | 'degraded' | 'unhealthy';
  summary: {
    total_processed: number;
    total_dropped: number;
    total_errors: number;
    drop_rate: number;
    error_rate: number;
  };
  drops_by_service: Record<string, Record<string, number>>;
  processed_by_service: Record<string, Record<string, number>>;
  timestamp: string;
}

// ============================================================================
// Service Config Types (for Services/Prompts pages)
// ============================================================================

export interface ServiceConfig {
  name: string;
  service_name: string;
  description?: string;
  version?: string;
  enabled: boolean;
  config: Record<string, unknown>;
  updated_at: string;
}

export interface ServicePrompt {
  name: string;
  service: string;
  service_name: string;
  prompt_name: string;
  description?: string;
  content: string;
  updated_at: string;
}

// ============================================================================
// API Error Type
// ============================================================================

export interface APIErrorData {
  detail?: string;
  message?: string;
  [key: string]: unknown;
}
