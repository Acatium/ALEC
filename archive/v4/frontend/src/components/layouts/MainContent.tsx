import { useUIStore } from '@/stores/uiStore';
import { Button } from '@/components/ui/Button';
import { PanelLeftIcon, PanelRightIcon } from '@/components/ui/Icons';

interface MainContentProps {
  children: React.ReactNode;
}

export function MainContent({ children }: MainContentProps) {
  const { sidebarOpen, toggleSidebar, rightPanelOpen, toggleRightPanel } = useUIStore();

  return (
    <main className="flex h-screen flex-1 flex-col overflow-hidden">
      {/* Top Header - Minimal like claude.ai */}
      <header className="flex items-center justify-between border-b bg-background px-6 py-2.5">
        <div className="flex items-center gap-3">
          {!sidebarOpen && (
            <Button variant="ghost" size="icon" onClick={toggleSidebar} className="h-8 w-8">
              <PanelLeftIcon className="h-4 w-4" />
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Right panel toggle - only show if there's content */}
          {!rightPanelOpen && (
            <Button variant="ghost" size="icon" onClick={toggleRightPanel} className="h-8 w-8">
              <PanelRightIcon className="h-4 w-4" />
            </Button>
          )}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="flex-1 overflow-hidden">{children}</div>
    </main>
  );
}

// Simple wrapper for pages that need standard padding
export function PageContainer({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-7xl mx-auto">
        {children}
      </div>
    </div>
  );
}
