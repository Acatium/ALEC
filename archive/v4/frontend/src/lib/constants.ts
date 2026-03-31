/**
 * Application constants
 */

// API
export const API_BASE = '/api/v1';

// Pagination
export const DEFAULT_PAGE_SIZE = 50;
export const MAX_PAGE_SIZE = 200;

// Polling intervals (ms)
export const POLLING_INTERVAL_FAST = 5_000;    // 5s - for running experiments
export const POLLING_INTERVAL_NORMAL = 30_000; // 30s - for general data
export const POLLING_INTERVAL_SLOW = 60_000;   // 1min - for rarely changing data

// Stale times (ms)
export const STALE_TIME_FAST = 5_000;
export const STALE_TIME_NORMAL = 30_000;
export const STALE_TIME_SLOW = 60_000;

// Debounce delays (ms)
export const DEBOUNCE_SEARCH = 300;
export const DEBOUNCE_RESIZE = 100;

// Local storage keys
export const STORAGE_KEYS = {
  UI_STORE: 'alec-ui-store',
  CHAT_STORE: 'alec-chat-store',
} as const;

// Route paths
export const ROUTES = {
  HOME: '/',
  SESSIONS: '/sessions',
  SESSION_DETAIL: '/sessions/:sessionId',
  BULLETS: '/bullets',
  BULLET_DETAIL: '/bullets/:bulletId',
  KNOWLEDGE_GRAPH: '/knowledge-graph',
  EVALUATION: '/evaluation',
  EVALUATION_NEW: '/evaluation/new',
  EVALUATION_DETAIL: '/evaluation/:id',
  EVALUATION_COMPARE: '/evaluation/compare/:idA/:idB',
  EPOCHS_COMPARISON: '/evaluation/epochs',
  SYSTEM: '/system',
  SERVICES: '/system/services',
  SERVICE_CONFIG: '/system/services/:serviceName',
  PROMPTS: '/system/prompts',
  PROMPT_EDITOR: '/system/prompts/:serviceName/:promptName',
  LEARNING_LOOP: '/learning-loop',
} as const;

// Bullet statuses
export const BULLET_STATUSES = ['candidate', 'active', 'archived', 'banned'] as const;

// Bullet polarities with labels
export const BULLET_POLARITIES = [
  { value: 'do', label: 'Solutions', color: 'green' },
  { value: 'dont', label: 'Constraints', color: 'red' },
  { value: 'know', label: 'Reference', color: 'blue' },
] as const;

// Micro-outcomes with labels
export const MICRO_OUTCOMES = [
  { value: 'progress', label: 'Progress', color: 'blue' },
  { value: 'solved', label: 'Solved', color: 'green' },
  { value: 'stuck', label: 'Stuck', color: 'yellow' },
  { value: 'error', label: 'Error', color: 'red' },
] as const;

// Experiment statuses
export const EXPERIMENT_STATUSES = ['pending', 'running', 'stopped', 'completed', 'failed'] as const;

// Dataset options
export const DATASETS = [
  { value: 'test_normal', label: 'Test Normal' },
  { value: 'train', label: 'Train' },
  { value: 'test_hard', label: 'Test Hard' },
  { value: 'validation', label: 'Validation' },
] as const;
