/**
 * Chat API - /api/v1/chat endpoints
 *
 * CRITICAL: These endpoints are used by evaluation framework.
 * See: core/session/api/routes.py
 */

import { api, buildQueryString } from './client';
import type {
  ChatRequest,
  ChatResponse,
  SessionCreate,
  SessionResponse,
  SessionListResponse,
  SessionCompleteRequest,
  SessionHistoryResponse,
  SessionTurnsResponse,
  SessionBulletsResponse,
} from './types';

// ============================================================================
// Request Types
// ============================================================================

export interface SessionListParams {
  status?: string;
  domain?: string;
  bullet_id?: string;
  limit?: number;
  offset?: number;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Send a message and get response
 * CRITICAL: Used by evaluation/appworld/runner/alec_client.py
 */
export async function sendMessage(request: ChatRequest): Promise<ChatResponse> {
  return api.post<ChatResponse>('/chat/message', request);
}

/**
 * Stream a message response via SSE
 */
export function streamMessage(
  request: ChatRequest,
  onMessage: (chunk: string) => void,
  onDone: (sessionId: string) => void,
  onError: (error: Error) => void
): () => void {
  const controller = new AbortController();

  fetch('/api/v1/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`Stream failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) {
        throw new Error('No response body');
      }

      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('event: ')) {
            // Event type line - next line should be data
            continue;
          }
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            // Check if this is the done event (contains session ID)
            if (data.match(/^[0-9a-f-]{36}$/i)) {
              onDone(data);
            } else {
              onMessage(data);
            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== 'AbortError') {
        onError(error);
      }
    });

  // Return cleanup function
  return () => controller.abort();
}

/**
 * Create a new session
 * CRITICAL: Used by evaluation framework
 */
export async function createSession(request: SessionCreate = {}): Promise<SessionResponse> {
  return api.post<SessionResponse>('/chat/sessions', request);
}

/**
 * List sessions with optional filters
 */
export async function listSessions(params: SessionListParams = {}): Promise<SessionListResponse> {
  const query = buildQueryString(params as Record<string, unknown>);
  return api.get<SessionListResponse>(`/chat/sessions${query}`);
}

/**
 * Get session by ID
 * CRITICAL: Used by evaluation/appworld/runner/alec_client.py
 */
export async function getSession(sessionId: string): Promise<SessionResponse> {
  return api.get<SessionResponse>(`/chat/sessions/${sessionId}`);
}

/**
 * Get session conversation history
 */
export async function getSessionHistory(sessionId: string): Promise<SessionHistoryResponse> {
  return api.get<SessionHistoryResponse>(`/chat/sessions/${sessionId}/history`);
}

/**
 * Complete a session
 * Emits session.ended event for learning loop
 */
export async function completeSession(
  sessionId: string,
  request: SessionCompleteRequest
): Promise<SessionResponse> {
  return api.post<SessionResponse>(`/chat/sessions/${sessionId}/complete`, request);
}

/**
 * Get session turns with micro-outcomes
 */
export async function getSessionTurns(sessionId: string): Promise<SessionTurnsResponse> {
  return api.get<SessionTurnsResponse>(`/chat/sessions/${sessionId}/turns`);
}

/**
 * Get bullets used in a session
 */
export async function getSessionBullets(sessionId: string): Promise<SessionBulletsResponse> {
  return api.get<SessionBulletsResponse>(`/chat/sessions/${sessionId}/bullets`);
}

// ============================================================================
// Export as namespace
// ============================================================================

export const chatApi = {
  sendMessage,
  streamMessage,
  createSession,
  listSessions,
  getSession,
  getSessionHistory,
  getSessionTurns,
  completeSession,
  getSessionBullets,
};
