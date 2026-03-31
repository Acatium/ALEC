import { Sidebar } from './Sidebar';
import { MainContent } from './MainContent';
import { RightPanel } from './RightPanel';

interface AppLayoutProps {
  children: React.ReactNode;
  rightPanelContent?: React.ReactNode;
}

export function AppLayout({ children, rightPanelContent }: AppLayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <MainContent>{children}</MainContent>
      <RightPanel>{rightPanelContent}</RightPanel>
    </div>
  );
}
