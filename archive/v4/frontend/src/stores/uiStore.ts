/**
 * UI Store - Theme, sidebar, notifications
 */

import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

interface Notification {
  id: string;
  type: 'info' | 'success' | 'warning' | 'error';
  message: string;
  timestamp: Date;
}

interface UIState {
  // Theme
  theme: 'light' | 'dark';
  setTheme: (theme: 'light' | 'dark') => void;
  toggleTheme: () => void;

  // Sidebar
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Right Panel
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  toggleRightPanel: () => void;

  // Notifications
  notifications: Notification[];
  addNotification: (type: Notification['type'], message: string) => void;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
}

export const useUIStore = create<UIState>()(
  devtools(
    persist(
      (set) => ({
        // Theme
        theme: 'dark',
        setTheme: (theme) => set({ theme }),
        toggleTheme: () =>
          set((state) => ({ theme: state.theme === 'light' ? 'dark' : 'light' })),

        // Sidebar - Start open so navigation is visible
        sidebarOpen: true,
        setSidebarOpen: (open) => set({ sidebarOpen: open }),
        toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

        // Right Panel
        rightPanelOpen: false,
        setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
        toggleRightPanel: () => set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),

        // Notifications
        notifications: [],
        addNotification: (type, message) =>
          set((state) => ({
            notifications: [
              ...state.notifications,
              {
                id: `${Date.now()}-${Math.random()}`,
                type,
                message,
                timestamp: new Date(),
              },
            ],
          })),
        removeNotification: (id) =>
          set((state) => ({
            notifications: state.notifications.filter((n) => n.id !== id),
          })),
        clearNotifications: () => set({ notifications: [] }),
      }),
      {
        name: 'alec-ui-store',
        partialize: (state) => ({
          theme: state.theme,
          sidebarOpen: state.sidebarOpen,
          rightPanelOpen: state.rightPanelOpen,
        }),
      }
    ),
    { name: 'UIStore' }
  )
);
