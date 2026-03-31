import { AppLayout } from '@/components/layouts/AppLayout';
import { ChatInterface } from '@/components/chat/ChatInterface';

export function HomePage() {
  return (
    <AppLayout>
      <div className="h-full">
        <ChatInterface />
      </div>
    </AppLayout>
  );
}

export default HomePage;
