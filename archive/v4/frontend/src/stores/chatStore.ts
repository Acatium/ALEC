/**
 * Chat Store - Current session and optimistic messages
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface OptimisticMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
}

interface ChatState {
  // Current session
  currentSessionId: string | null;
  setCurrentSession: (sessionId: string | null) => void;

  // Optimistic messages (not yet confirmed by server)
  optimisticMessages: OptimisticMessage[];
  addOptimisticMessage: (message: OptimisticMessage) => void;
  removeOptimisticMessage: (id: string) => void;
  clearOptimisticMessages: () => void;
}

export const useChatStore = create<ChatState>()(
  devtools(
    persist(
      (set) => ({
        // Current session
        currentSessionId: null,
        setCurrentSession: (sessionId) => set({ currentSessionId: sessionId }),

        // Optimistic messages
        optimisticMessages: [],
        addOptimisticMessage: (message) =>
          set((state) => ({
            optimisticMessages: [...state.optimisticMessages, message],
          })),
        removeOptimisticMessage: (id) =>
          set((state) => ({
            optimisticMessages: state.optimisticMessages.filter((m) => m.id !== id),
          })),
        clearOptimisticMessages: () => set({ optimisticMessages: [] }),
      }),
      {
        name: 'alec-chat-store',
        partialize: (state) => ({
          currentSessionId: state.currentSessionId,
        }),
      }
    ),
    { name: 'ChatStore' }
  )
);
