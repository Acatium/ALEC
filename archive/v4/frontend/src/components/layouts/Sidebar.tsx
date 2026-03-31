import { useState, useEffect } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { useUIStore } from '@/stores/uiStore';
import { Button } from '@/components/ui/Button';
import {
  ChevronLeftIcon,
  PlusIcon,
  MessageSquareIcon,
  ListIcon,
  BookOpenIcon,
  NetworkIcon,
  BrainIcon,
  SettingsIcon,
  FlaskIcon,
} from '@/components/ui/Icons';
import { cn } from '@/lib/utils';
import { formatTimeAgo as formatTimeAgoUtil } from '@/utils/dateFormat';

interface Session {
  session_id: string;
  title: string;
  domain: string;
  status: 'active' | 'completed' | 'failed';
  message_count: number;
  created_at: string;
  updated_at: string;
}

interface NavItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
  isActive: boolean;
  color?: string;
}

function NavItem({ to, icon, label, isActive, color = 'blue' }: NavItemProps) {
  const colorClasses = {
    blue: 'text-blue-500 bg-blue-500/10 border-blue-500/30',
    purple: 'text-purple-500 bg-purple-500/10 border-purple-500/30',
    green: 'text-green-500 bg-green-500/10 border-green-500/30',
    amber: 'text-amber-500 bg-amber-500/10 border-amber-500/30',
    rose: 'text-rose-500 bg-rose-500/10 border-rose-500/30',
  };

  return (
    <Link
      to={to}
      className={cn(
        'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
        isActive
          ? `${colorClasses[color as keyof typeof colorClasses]} border`
          : 'text-muted-foreground hover:text-foreground hover:bg-muted'
      )}
    >
      <span className={cn('flex-shrink-0', isActive && colorClasses[color as keyof typeof colorClasses].split(' ')[0])}>
        {icon}
      </span>
      <span>{label}</span>
    </Link>
  );
}

export function Sidebar() {
  const { sidebarOpen, toggleSidebar } = useUIStore();
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [sessionsExpanded, setSessionsExpanded] = useState(false);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loadingSessions, setLoadingSessions] = useState(false);

  const currentSessionId = searchParams.get('session');

  // Fetch sessions when expanded
  useEffect(() => {
    if (sessionsExpanded) {
      fetchRecentSessions();
    }
  }, [sessionsExpanded]);

  const fetchRecentSessions = async () => {
    setLoadingSessions(true);
    try {
      const response = await fetch('/api/v1/chat/sessions?limit=10&sort=updated_at&order=desc');
      if (!response.ok) throw new Error('Failed to fetch sessions');
      const data = await response.json();
      setSessions(data.sessions || []);
    } catch (error) {
      console.error('Error fetching sessions:', error);
    } finally {
      setLoadingSessions(false);
    }
  };

  const handleNewChat = () => {
    navigate('/');
  };

  const handleSessionClick = (sessionId: string) => {
    navigate(`/?session=${sessionId}`);
  };

  const formatTimeAgo = (dateString: string) => {
    return formatTimeAgoUtil(dateString);
  };

  return (
    <aside
      className={cn(
        'flex h-screen flex-col border-r bg-gradient-to-b from-background to-muted/30 transition-all duration-300',
        sidebarOpen ? 'w-64' : 'w-0 border-r-0'
      )}
    >
      {sidebarOpen && (
        <div className="flex h-full flex-col">
          {/* Sidebar Header */}
          <div className="flex items-center justify-between border-b px-4 py-5">
            <div className="flex-1 min-w-0">
              <div className="text-4xl font-bold tracking-tight text-foreground">ALEC</div>
              <div className="text-base text-muted-foreground leading-tight mt-1">
                <span className="block">Agent Learning +</span>
                <span className="block">Evolving Context</span>
              </div>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="flex-shrink-0 h-8 w-8 hover:bg-muted"
            >
              <ChevronLeftIcon className="h-4 w-4" />
            </Button>
          </div>

          {/* Navigation Items */}
          <div className="flex-1 overflow-y-auto py-4 px-3">
            {/* Chat Section */}
            <div className="mb-6">
              <div className="flex items-center gap-2 mb-2">
                <button
                  onClick={() => setSessionsExpanded(!sessionsExpanded)}
                  className="flex-shrink-0 p-1 rounded hover:bg-muted transition-colors"
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                    className={cn(
                      'w-3 h-3 text-muted-foreground transition-transform',
                      sessionsExpanded && 'rotate-90'
                    )}
                  >
                    <path
                      fillRule="evenodd"
                      d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"
                      clipRule="evenodd"
                    />
                  </svg>
                </button>
                <Link
                  to="/"
                  className={cn(
                    'flex-1 flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-200',
                    location.pathname === '/' && !currentSessionId
                      ? 'text-blue-500 bg-blue-500/10 border border-blue-500/30'
                      : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  )}
                >
                  <MessageSquareIcon className="h-4 w-4" />
                  <span>Chat</span>
                </Link>
                <button
                  onClick={handleNewChat}
                  className="flex-shrink-0 p-2 rounded-lg bg-blue-500/10 text-blue-500 hover:bg-blue-500/20 transition-colors"
                  title="New Chat"
                >
                  <PlusIcon className="w-4 h-4" />
                </button>
              </div>

              {/* Sessions List */}
              {sessionsExpanded && (
                <div className="ml-6 mt-1 space-y-1 border-l-2 border-muted pl-3">
                  {loadingSessions ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">Loading...</div>
                  ) : sessions.length === 0 ? (
                    <div className="px-3 py-2 text-xs text-muted-foreground">No sessions yet</div>
                  ) : (
                    <>
                      {sessions.map((session) => {
                        const isActive = currentSessionId === session.session_id;
                        return (
                          <button
                            key={session.session_id}
                            onClick={() => handleSessionClick(session.session_id)}
                            className={cn(
                              'w-full text-left px-3 py-2 rounded-lg text-xs transition-all duration-200',
                              isActive
                                ? 'bg-blue-500/10 text-blue-500 border border-blue-500/30'
                                : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                            )}
                          >
                            <div className="truncate font-medium">{session.title || 'Untitled Chat'}</div>
                            <div className="flex items-center justify-between opacity-70 mt-0.5">
                              <span>{session.message_count} msgs</span>
                              <span>{formatTimeAgo(session.updated_at)}</span>
                            </div>
                          </button>
                        );
                      })}
                      <Link
                        to="/sessions"
                        className="block w-full text-left px-3 py-2 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                      >
                        View all sessions →
                      </Link>
                    </>
                  )}
                </div>
              )}
            </div>

            {/* Insights Section */}
            <div className="mb-6">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 px-3 mb-2">
                Insights
              </div>
              <div className="space-y-1">
                <NavItem
                  to="/sessions"
                  icon={<ListIcon className="h-4 w-4" />}
                  label="All Sessions"
                  isActive={location.pathname === '/sessions'}
                  color="blue"
                />
                <NavItem
                  to="/bullets"
                  icon={<BookOpenIcon className="h-4 w-4" />}
                  label="Library"
                  isActive={location.pathname === '/bullets'}
                  color="purple"
                />
                <NavItem
                  to="/knowledge-graph"
                  icon={<NetworkIcon className="h-4 w-4" />}
                  label="Knowledge Graph"
                  isActive={location.pathname === '/knowledge-graph'}
                  color="green"
                />
              </div>
            </div>

            {/* Learning Management Section */}
            <div className="mb-6">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60 px-3 mb-2">
                Learning
              </div>
              <div className="space-y-1">
                <NavItem
                  to="/learning-loop"
                  icon={<BrainIcon className="h-4 w-4" />}
                  label="Learning Loop"
                  isActive={location.pathname === '/learning-loop'}
                  color="amber"
                />
                <NavItem
                  to="/system"
                  icon={<SettingsIcon className="h-4 w-4" />}
                  label="System"
                  isActive={location.pathname === '/system'}
                  color="rose"
                />
                <NavItem
                  to="/evaluation"
                  icon={<FlaskIcon className="h-4 w-4" />}
                  label="Evaluation"
                  isActive={location.pathname.startsWith('/evaluation')}
                  color="green"
                />
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-t px-4 py-3">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>v3.0</span>
              <span className="flex items-center gap-1">
                <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
                Connected
              </span>
            </div>
          </div>
        </div>
      )}
    </aside>
  );
}
