import { useUIStore } from '@/stores/uiStore';
import { Button } from '@/components/ui/Button';
import { ChevronRightIcon } from '@/components/ui/Icons';
import { cn } from '@/lib/utils';

interface RightPanelProps {
  children?: React.ReactNode;
}

export function RightPanel({ children }: RightPanelProps) {
  const rightPanelOpen = useUIStore((state) => state.rightPanelOpen);
  const toggleRightPanel = useUIStore((state) => state.toggleRightPanel);

  return (
    <aside
      className={cn(
        'flex h-screen flex-col border-l bg-muted/20 transition-all duration-300',
        rightPanelOpen ? 'w-[40%] min-w-[400px] max-w-[700px]' : 'w-0 border-l-0',
      )}
    >
      {rightPanelOpen && (
        <div className="flex h-full flex-col">
          {/* Panel Header */}
          <div className="flex items-center justify-between border-b bg-background px-6 py-2.5">
            <h3 className="font-semibold text-base">Generated Artifacts</h3>
            <Button variant="ghost" size="icon" onClick={toggleRightPanel} className="h-8 w-8">
              <ChevronRightIcon className="h-4 w-4" />
            </Button>
          </div>

          {/* Panel Content */}
          <div className="flex-1 overflow-y-auto p-6 bg-muted/10">
            {children || (
              <div className="flex h-full items-center justify-center text-base text-muted-foreground">
                No output to display
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
