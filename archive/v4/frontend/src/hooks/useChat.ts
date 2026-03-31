import { useCallback, useEffect, useRef, useState } from 'react';

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, any>;
}

export interface ChatSession {
  sessionId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  error: string | null;
}

interface SendMessageRequest {
  message: string;
  session_id?: string;
}

interface ApiMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

const API_BASE = '/api/v1/chat';
const SESSION_STORAGE_KEY = 'alec_current_session_id';

export function useChat(initialSessionId?: string) {
  const [session, setSession] = useState<ChatSession>({
    sessionId: initialSessionId || null,
    messages: [],
    isStreaming: false,
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  // Save session ID to sessionStorage
  const saveSessionId = useCallback((sessionId: string) => {
    sessionStorage.setItem(SESSION_STORAGE_KEY, sessionId);
  }, []);

  // Clear session ID from sessionStorage
  const clearSessionId = useCallback(() => {
    sessionStorage.removeItem(SESSION_STORAGE_KEY);
  }, []);

  // Create a new session
  const createSession = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/sessions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ metadata: {} }),
      });

      if (!response.ok) throw new Error('Failed to create session');

      const data = await response.json();
      const sessionId = data.session_id;
      setSession((prev) => ({ ...prev, sessionId }));
      saveSessionId(sessionId);
      return sessionId;
    } catch (error) {
      setSession((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
      return null;
    }
  }, [saveSessionId]);

  // Send a message with streaming response
  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      // Add user message immediately
      const userMessage: ChatMessage = {
        id: `user-${Date.now()}`,
        role: 'user',
        content,
        timestamp: new Date().toISOString(),
      };

      setSession((prev) => ({
        ...prev,
        messages: [...prev.messages, userMessage],
        isStreaming: true,
        error: null,
      }));

      try {
        // Prepare request body
        const body: SendMessageRequest = { message: content };
        if (session.sessionId) {
          body.session_id = session.sessionId;
        }

        // Send message to backend
        const response = await fetch(`${API_BASE}/message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });

        if (!response.ok) throw new Error('Failed to send message');

        const data = await response.json();

        // Update session ID if this was the first message
        if (!session.sessionId && data.session_id) {
          setSession((prev) => ({ ...prev, sessionId: data.session_id }));
          saveSessionId(data.session_id);
        }

        // Add assistant message
        const assistantMessage: ChatMessage = {
          id: `assistant-${Date.now()}`,
          role: 'assistant',
          content: data.message,
          timestamp: data.timestamp,
          metadata: { tool_calls: data.tool_calls },
        };

        setSession((prev) => ({
          ...prev,
          messages: [...prev.messages, assistantMessage],
          isStreaming: false,
        }));
      } catch (error) {
        setSession((prev) => ({
          ...prev,
          isStreaming: false,
          error: error instanceof Error ? error.message : 'Unknown error',
        }));
      }
    },
    [session.sessionId, saveSessionId]
  );

  // Load session history
  const loadHistory = useCallback(async (sessionId: string) => {
    try {
      const response = await fetch(`${API_BASE}/sessions/${sessionId}`);
      if (!response.ok) throw new Error('Failed to load history');

      const data = await response.json();
      setSession({
        sessionId: data.session_id,
        messages: data.messages.map((msg: ApiMessage) => ({
          id: msg.id,
          role: msg.role,
          content: msg.content,
          timestamp: msg.timestamp,
          metadata: msg.metadata,
        })),
        isStreaming: false,
        error: null,
      });
    } catch (error) {
      setSession((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : 'Unknown error',
      }));
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return {
    session,
    sendMessage,
    createSession,
    loadHistory,
    clearSessionId,
  };
}
