import { useState, useEffect, useRef } from 'react';
import { HashRouter, Routes, Route, Link, useLocation, useParams } from 'react-router-dom';
import {
  MessageSquare, List, BookOpen, Network, Brain, Settings, FlaskConical, Plus,
  ChevronLeft, ChevronRight, ChevronUp, ChevronDown, Send, Check, AlertTriangle,
  PlayCircle, StopCircle, Trash2, BarChart3, Zap, Database, TrendingUp
} from 'lucide-react';
import {
  XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area,
  ComposedChart, Line, Legend
} from 'recharts';
import mermaid from 'mermaid';
import './index.css';

// Initialize mermaid with custom theme for larger text
mermaid.initialize({
  startOnLoad: false,
  theme: 'base',
  themeVariables: {
    primaryColor: '#6366f1',
    primaryTextColor: '#1f2937',
    primaryBorderColor: '#4f46e5',
    lineColor: '#6b7280',
    secondaryColor: '#f3f4f6',
    tertiaryColor: '#fef3c7',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    fontSize: '52px',
    actorBkg: '#f3f4f6',
    actorBorder: '#d1d5db',
    actorTextColor: '#1f2937',
    signalColor: '#374151',
    signalTextColor: '#1f2937',
    noteBkgColor: '#fef3c7',
    noteTextColor: '#92400e',
    noteBorderColor: '#fcd34d',
  },
  sequence: {
    diagramMarginX: 8,
    diagramMarginY: 16,
    actorMargin: 20,
    width: 130,
    height: 70,
    boxMargin: 4,
    boxTextMargin: 4,
    noteMargin: 8,
    messageMargin: 35,
    useMaxWidth: true,
    wrap: true,
  },
});

// Mermaid component for rendering diagrams
function MermaidDiagram({ chart, className = '' }: { chart: string; className?: string }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [svg, setSvg] = useState<string>('');

  useEffect(() => {
    const renderChart = async () => {
      if (!containerRef.current) return;
      try {
        const id = `mermaid-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
        const { svg: renderedSvg } = await mermaid.render(id, chart);
        setSvg(renderedSvg);
      } catch (err) {
        console.error('Mermaid render error:', err);
      }
    };
    renderChart();
  }, [chart]);

  return (
    <div
      ref={containerRef}
      className={`overflow-x-auto ${className}`}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}

const OVERVIEW_DIAGRAM = `
sequenceDiagram
    participant S as Session
    participant K as Kafka
    participant AD as ADVISOR
    participant RF as REFLECTOR
    participant CU as CURATOR
    participant CL as CLUSTERER
    participant LB as LIBRARIAN
    participant ST as STRATEGIST
    participant DB as Postgres

    Note over S,DB: Per-Turn Flow
    S->>K: bullets.requested
    K->>AD: consume
    AD->>DB: vector search
    AD->>AD: Thompson Sampling
    AD-->>S: Redis
    S->>S: Claude API
    S->>K: llm.response
    K->>RF: buffer

    Note over S,DB: Session End
    S->>K: session.ended
    K->>RF: analyze
    RF->>DB: counters
    RF->>DB: edges
    RF->>K: aku.proposed
    RF->>K: attribution

    K->>CU: aku
    CU->>DB: dedup
    alt new
        CU->>DB: INSERT
        CU->>K: accepted
    else dup
        CU->>DB: evidence++
    end

    K->>CL: attribution
    CL->>DB: cluster
    CL->>DB: solved_by

    Note over LB,ST: Strategic
    LB->>DB: gaps
    LB->>K: gap.detected
    K->>ST: synthesize
    ST->>K: aku.proposed
`;

const ADVISOR_DIAGRAM = `
sequenceDiagram
    autonumber
    participant S as Session
    participant K as Kafka
    participant A as ADVISOR
    participant R as Redis
    participant DB as PostgreSQL

    S->>K: bullets.requested
    Note right of S: {session_id, turn_number,<br/>domain, problem_context}
    K->>A: consume event

    alt Turn 1 (no cluster_id)
        A->>A: extract task from user input
        A->>DB: embed situation
        A->>DB: find nearest cluster
    else Turn 2+
        A->>R: get cached embedding
    end

    rect rgb(240, 249, 255)
        Note over A,DB: Two-Path Retrieval
        A->>DB: Vector search (threshold=0.50)
        A->>DB: Cluster solutions (solved_by)
        A->>A: merge unique bullets
    end

    rect rgb(254, 243, 199)
        Note over A,DB: Filtering & Scoring
        A->>DB: get caused_failure edges
        loop For each candidate
            A->>A: score = similarity * ts * decay
        end
        A->>A: filter TS floor, take top 8
    end

    A->>R: write bullets to Redis
`;

const REFLECTOR_DIAGRAM = `
sequenceDiagram
    autonumber
    participant S as Session
    participant K as Kafka
    participant R as REFLECTOR
    participant LLM as Claude API
    participant DB as PostgreSQL

    Note over S,R: Turn Buffering
    S->>K: llm.response.received
    K->>R: buffer in memory

    Note over S,R: Session Analysis
    S->>K: session.ended
    K->>R: trigger analysis
    R->>DB: fetch bullet content

    rect rgb(243, 232, 255)
        Note over R,LLM: LLM Turn Analysis
        R->>LLM: analyze turns prompt
        LLM-->>R: micro_outcome + attribution
    end

    rect rgb(254, 226, 226)
        Note over R,DB: Counter Updates
        loop For each bullet
            alt Helped
                R->>DB: helpful_count++
            else Harmed
                R->>DB: harmful_count++
                R->>DB: caused_failure edge
            end
        end
    end

    rect rgb(220, 252, 231)
        Note over R,K: AKU Extraction
        R->>R: find stuck→recovery
        R->>K: aku.proposed
    end

    R->>K: attribution.resolved
`;

const CURATOR_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant C as CURATOR
    participant E as Embedding API
    participant DB as PostgreSQL

    K->>C: aku.proposed

    rect rgb(254, 243, 199)
        Note over C: Quality Gate
        C->>C: validate assertion ≥ 20 chars
        C->>C: validate situation ≥ 10 chars
        C->>C: validate modality/polarity
    end

    rect rgb(219, 234, 254)
        Note over C,E: Embedding Generation
        C->>E: embed(situation)
        C->>E: embed(assertion)
    end

    rect rgb(243, 232, 255)
        Note over C,DB: Deduplication Check
        C->>DB: assertion similarity search
        alt Duplicate found
            C->>DB: evidence_count++
            C->>K: bullet.merged
        else New bullet
            C->>DB: INSERT bullet
            C->>K: bullet.accepted
        end
    end
`;

const CLUSTERER_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant Cl as CLUSTERER
    participant DB as PostgreSQL

    rect rgb(219, 234, 254)
        Note over K,Cl: Handle attribution.resolved
        K->>Cl: attribution.resolved
        Cl->>DB: find/create cluster

        loop For each turn
            Cl->>DB: UPDATE session_turns
            alt stuck/error
                Cl->>DB: failure_count++
            else solved
                Cl->>DB: success_count++
            end
        end

        loop For each helped bullet
            Cl->>DB: UPSERT solved_by edge
        end
    end

    rect rgb(254, 243, 199)
        Note over Cl,DB: Status Transitions
        Cl->>DB: candidate → active (3+ helpful)
        Cl->>DB: active → archived (harmful)
    end

    rect rgb(220, 252, 231)
        Note over K,Cl: Handle bullet.accepted
        K->>Cl: bullet.accepted
        Cl->>DB: CREATE solved_by edge
    end
`;

const LIBRARIAN_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant L as LIBRARIAN
    participant DB as PostgreSQL

    K->>L: attribution.resolved
    L->>L: check cooldown (60s)

    rect rgb(254, 226, 226)
        Note over L,DB: Gap Detection
        L->>DB: clusters with failures, no solutions
        loop For each gap
            L->>K: library.gap.detected
        end
    end

    rect rgb(254, 243, 199)
        Note over L,DB: Struggling Detection
        L->>DB: clusters with solutions, <50% success
        loop For each struggling
            L->>K: library.cluster.struggling
        end
    end

    rect rgb(219, 234, 254)
        Note over L,DB: Auto-Archive
        L->>DB: archive harmful bullets
    end
`;

const STRATEGIST_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant St as STRATEGIST
    participant LLM as Claude API
    participant DB as PostgreSQL

    alt Gap Event
        K->>St: library.gap.detected
    else Struggling Event
        K->>St: library.cluster.struggling
    end

    rect rgb(243, 232, 255)
        Note over St: In-Memory Dedup
        St->>St: check processed set
    end

    rect rgb(219, 234, 254)
        Note over St,LLM: LLM Synthesis
        St->>LLM: synthesis prompt
        LLM-->>St: synthesized AKU
    end

    St->>St: validate AKU

    rect rgb(254, 243, 199)
        Note over St,DB: Pre-Synthesis Dedup
        St->>DB: assertion similarity > 0.90
        alt No duplicate
            St->>K: aku.proposed
        end
    end
`;

// Collapsible component for service details
function Collapsible({
  title,
  icon,
  badge,
  badgeColor,
  children,
  defaultOpen = false
}: {
  title: string;
  icon: string;
  badge: string;
  badgeColor: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const colors: Record<string, { bg: string; text: string; iconBg: string }> = {
    amber: { bg: 'bg-amber-50 hover:bg-amber-100', text: 'text-amber-700', iconBg: 'bg-amber-500' },
    purple: { bg: 'bg-purple-50 hover:bg-purple-100', text: 'text-purple-700', iconBg: 'bg-purple-500' },
    green: { bg: 'bg-green-50 hover:bg-green-100', text: 'text-green-700', iconBg: 'bg-green-500' },
    blue: { bg: 'bg-blue-50 hover:bg-blue-100', text: 'text-blue-700', iconBg: 'bg-blue-500' },
    slate: { bg: 'bg-slate-50 hover:bg-slate-100', text: 'text-slate-700', iconBg: 'bg-slate-500' },
    red: { bg: 'bg-red-50 hover:bg-red-100', text: 'text-red-700', iconBg: 'bg-red-500' },
  };
  const color = colors[badgeColor] || colors.slate;

  return (
    <div className="rounded-xl border overflow-hidden">
      <button
        className={`w-full flex items-center gap-3 p-4 text-left transition-colors ${color.bg}`}
        onClick={() => setIsOpen(!isOpen)}
      >
        <ChevronRight className={`h-5 w-5 transition-transform ${isOpen ? 'rotate-90' : ''} ${color.text}`} />
        <span className={`flex h-10 w-10 items-center justify-center rounded-lg text-base font-bold text-white ${color.iconBg}`}>
          {icon}
        </span>
        <div className="flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{title}</span>
            <Badge className={`${color.bg} ${color.text}`}>{badge}</Badge>
          </div>
        </div>
      </button>
      {isOpen && (
        <div className="border-t bg-white p-6">
          {children}
        </div>
      )}
    </div>
  );
}

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface Turn {
  turn_id: string;
  turn_number: number;
  user_message: string;
  assistant_response: string;
  sub_task: string;
  micro_outcome: string;
  bullets_shown: string[];
  bullets_helped: string[];
  bullets_harmed: string[];
  created_at: string;
}

// ============================================================================
// MOCK DATA - Comprehensive realistic data
// ============================================================================

const MOCK_SESSIONS = [
  {
    id: 'a1b2c3d4-e5f6-7890-abcd-ef1234567890',
    title: 'Spotify playlist analysis task',
    domain: 'spotify',
    status: 'completed',
    message_count: 16,
    created_at: '2024-12-12T10:30:00Z',
    updated_at: '2024-12-12T10:45:00Z',
    micro_outcomes: { solved: 5, progress: 8, stuck: 2, error: 1 },
    success: true,
  },
  {
    id: 'b2c3d4e5-f6a7-8901-bcde-f23456789012',
    title: 'Weather API data extraction',
    domain: 'weather',
    status: 'completed',
    message_count: 10,
    created_at: '2024-12-12T09:15:00Z',
    updated_at: '2024-12-12T09:28:00Z',
    micro_outcomes: { solved: 3, progress: 5, stuck: 1, error: 1 },
    success: true,
  },
  {
    id: 'c3d4e5f6-a7b8-9012-cdef-345678901234',
    title: 'File management automation',
    domain: 'filesystem',
    status: 'completed',
    message_count: 24,
    created_at: '2024-12-11T14:00:00Z',
    updated_at: '2024-12-11T14:45:00Z',
    micro_outcomes: { solved: 2, progress: 10, stuck: 8, error: 4 },
    success: false,
  },
  {
    id: 'd4e5f6a7-b8c9-0123-defa-456789012345',
    title: 'Email composition helper',
    domain: 'email',
    status: 'completed',
    message_count: 8,
    created_at: '2024-12-11T11:20:00Z',
    updated_at: '2024-12-11T11:32:00Z',
    micro_outcomes: { solved: 3, progress: 4, stuck: 1, error: 0 },
    success: true,
  },
  {
    id: 'e5f6a7b8-c9d0-1234-efab-567890123456',
    title: 'Database query optimization',
    domain: 'database',
    status: 'active',
    message_count: 30,
    created_at: '2024-12-12T13:00:00Z',
    updated_at: '2024-12-12T13:25:00Z',
    micro_outcomes: { solved: 8, progress: 15, stuck: 5, error: 2 },
    success: null,
  },
];

const MOCK_TURNS: Turn[] = [
  {
    turn_id: 't1',
    turn_number: 1,
    user_message: 'Help me get all songs from my Spotify liked songs playlist and find which ones have a rating above 4 stars.',
    assistant_response: `I'll help you retrieve and filter your liked songs from Spotify. Let me start by fetching all your liked songs using the pagination API.

\`\`\`python
liked_songs = []
offset = 0
while True:
    batch = get_liked_songs(offset=offset, limit=50)
    liked_songs.extend(batch)
    if len(batch) < 50:
        break
    offset += 50
print(f"Found {len(liked_songs)} liked songs")
\`\`\`

I've retrieved all 347 songs from your liked songs playlist.`,
    sub_task: 'Retrieve all liked songs from Spotify',
    micro_outcome: 'solved',
    bullets_shown: ['blt-001', 'blt-003'],
    bullets_helped: ['blt-001'],
    bullets_harmed: [],
    created_at: '2024-12-12T10:30:15Z',
  },
  {
    turn_id: 't2',
    turn_number: 2,
    user_message: 'Great, now filter to only songs with rating above 4.',
    assistant_response: `I'll filter the songs by rating. Note that the standard API doesn't return ratings directly - I need to check the private API for this information.

\`\`\`python
high_rated = []
for song in liked_songs:
    details = show_song_privates(song.id)
    if hasattr(details, 'rating') and details.rating > 4:
        high_rated.append({
            'name': song.name,
            'artist': song.artist,
            'rating': details.rating
        })
print(f"Found {len(high_rated)} songs rated above 4 stars")
\`\`\`

Found 47 songs with ratings above 4 stars.`,
    sub_task: 'Filter songs by rating using private API',
    micro_outcome: 'solved',
    bullets_shown: ['blt-002', 'blt-003'],
    bullets_helped: ['blt-002'],
    bullets_harmed: [],
    created_at: '2024-12-12T10:32:30Z',
  },
  {
    turn_id: 't3',
    turn_number: 3,
    user_message: 'Can you also get the play count for each of these songs?',
    assistant_response: `I'll retrieve the play count for each high-rated song. The play count is also available through the private API.

\`\`\`python
for song in high_rated:
    details = show_song_privates(song['id'])
    song['play_count'] = details.play_count if hasattr(details, 'play_count') else 0

# Sort by play count descending
high_rated.sort(key=lambda x: x['play_count'], reverse=True)
print(f"Top 5 most played high-rated songs:")
for song in high_rated[:5]:
    print(f"  {song['name']} - {song['play_count']} plays")
\`\`\`

Retrieved play counts for all 47 songs. Your most played high-rated song is "Bohemian Rhapsody" with 234 plays.`,
    sub_task: 'Get play counts for filtered songs',
    micro_outcome: 'solved',
    bullets_shown: ['blt-002'],
    bullets_helped: ['blt-002'],
    bullets_harmed: [],
    created_at: '2024-12-12T10:35:00Z',
  },
  {
    turn_id: 't4',
    turn_number: 4,
    user_message: 'Now create a new playlist with these songs.',
    assistant_response: `I'll create a new playlist and add all the high-rated songs to it.

\`\`\`python
# Create new playlist
playlist = create_playlist(
    name="High Rated Favorites",
    description="Songs rated above 4 stars"
)

# Add songs to playlist
song_ids = [song['id'] for song in high_rated]
add_songs_to_playlist(playlist.id, song_ids)
print(f"Created playlist '{playlist.name}' with {len(song_ids)} songs")
\`\`\`

Successfully created playlist "High Rated Favorites" with 47 songs.`,
    sub_task: 'Create playlist and add songs',
    micro_outcome: 'solved',
    bullets_shown: [],
    bullets_helped: [],
    bullets_harmed: [],
    created_at: '2024-12-12T10:37:15Z',
  },
  {
    turn_id: 't5',
    turn_number: 5,
    user_message: 'The playlist creation failed. It says the playlist already exists.',
    assistant_response: `I see - there's already a playlist with that name. Let me check if it exists and either update it or create one with a different name.

\`\`\`python
# Check for existing playlist
existing = get_playlists()
matching = [p for p in existing if p.name == "High Rated Favorites"]

if matching:
    # Clear and update existing playlist
    playlist = matching[0]
    clear_playlist(playlist.id)
    add_songs_to_playlist(playlist.id, song_ids)
    print(f"Updated existing playlist with {len(song_ids)} songs")
else:
    # This shouldn't happen based on the error...
    pass
\`\`\`

I'm getting an error when trying to clear the playlist. Let me investigate...`,
    sub_task: 'Handle existing playlist conflict',
    micro_outcome: 'stuck',
    bullets_shown: ['blt-003'],
    bullets_helped: [],
    bullets_harmed: ['blt-003'],
    created_at: '2024-12-12T10:40:00Z',
  },
];

const MOCK_BULLETS = [
  {
    id: 'blt-001',
    situation: 'When iterating through all items in a paginated API collection',
    assertion: 'Use offset=0 for first page. Loop with while True. Stop when response length < page_size. This handles edge cases where total count is unknown.',
    category: 'solutions',
    polarity: 'do',
    status: 'active',
    helpful_count: 67,
    harmful_count: 3,
    neutral_count: 18,
    evidence_count: 12,
    created_at: '2024-12-05T08:00:00Z',
  },
  {
    id: 'blt-002',
    situation: 'When extracting metrics that are not in standard API responses',
    assertion: 'Check for _privates() or hidden endpoints. Many APIs have undocumented internal methods that expose additional data like ratings, play counts, and internal flags.',
    category: 'solutions',
    polarity: 'do',
    status: 'active',
    helpful_count: 45,
    harmful_count: 8,
    neutral_count: 12,
    evidence_count: 8,
    created_at: '2024-12-07T14:30:00Z',
  },
  {
    id: 'blt-003',
    situation: 'When API returns inconsistent response formats across endpoints',
    assertion: 'API response format varies by endpoint: some return {items: [...]} (dict), others return raw list. Always check type first before accessing .items or iterating directly.',
    category: 'constraints',
    polarity: 'know',
    status: 'active',
    helpful_count: 89,
    harmful_count: 2,
    neutral_count: 21,
    evidence_count: 15,
    created_at: '2024-12-03T10:15:00Z',
  },
  {
    id: 'blt-004',
    situation: 'When generating SQL queries involving table joins on large datasets',
    assertion: 'Test SQL performance before returning. JOINs on large tables without indexes can timeout. Use EXPLAIN ANALYZE to verify query plan.',
    category: 'constraints',
    polarity: 'do',
    status: 'candidate',
    helpful_count: 23,
    harmful_count: 2,
    neutral_count: 8,
    evidence_count: 4,
    created_at: '2024-12-10T16:45:00Z',
  },
  {
    id: 'blt-005',
    situation: 'When debugging API authentication failures',
    assertion: 'Check token expiry FIRST. Most auth failures (>80%) are expired tokens, not invalid credentials. Use token introspection endpoint if available.',
    category: 'meta_prompts',
    polarity: 'do',
    status: 'active',
    helpful_count: 56,
    harmful_count: 12,
    neutral_count: 34,
    evidence_count: 9,
    created_at: '2024-12-06T09:00:00Z',
  },
  {
    id: 'blt-006',
    situation: 'When handling file operations on paths that may not exist',
    assertion: 'Always verify directory exists before write. Use os.makedirs with exist_ok=True for recursive creation.',
    category: 'cheat_sheets',
    polarity: 'do',
    status: 'archived',
    helpful_count: 8,
    harmful_count: 23,
    neutral_count: 5,
    evidence_count: 6,
    created_at: '2024-11-28T11:30:00Z',
  },
  {
    id: 'blt-007',
    situation: 'When making multiple sequential API calls that depend on each other',
    assertion: 'Implement exponential backoff for rate limiting. Start with 100ms delay, double on each retry, cap at 30s. Most APIs return 429 status for rate limits.',
    category: 'solutions',
    polarity: 'do',
    status: 'active',
    helpful_count: 78,
    harmful_count: 4,
    neutral_count: 15,
    evidence_count: 11,
    created_at: '2024-12-04T13:20:00Z',
  },
  {
    id: 'blt-008',
    situation: 'When parsing JSON responses that may have null or missing fields',
    assertion: 'Use .get() with default values instead of direct key access. This prevents KeyError exceptions when optional fields are missing.',
    category: 'constraints',
    polarity: 'do',
    status: 'active',
    helpful_count: 92,
    harmful_count: 1,
    neutral_count: 28,
    evidence_count: 14,
    created_at: '2024-12-02T15:00:00Z',
  },
];

// Learning story: System improves task success from 32% to 78%, assertions from 38% to 82%,
// while token usage DECREASES from 68K to 38K (more efficient as it learns)
const MOCK_EXPERIMENTS = [
  {
    id: 'exp-001',
    name: 'Epoch 1 - Initial Baseline',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.32,
    passed_assertions: 380,
    total_assertions: 1000,
    avg_tokens: 68200,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-01T08:00:00Z',
    started_at: '2024-12-01T08:01:00Z',
    completed_at: '2024-12-01T14:30:00Z',
  },
  {
    id: 'exp-002',
    name: 'Epoch 2 - First Learning',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.41,
    passed_assertions: 465,
    total_assertions: 1000,
    avg_tokens: 62400,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-03T09:00:00Z',
    started_at: '2024-12-03T09:02:00Z',
    completed_at: '2024-12-03T15:45:00Z',
  },
  {
    id: 'exp-003',
    name: 'Epoch 3 - Pattern Recognition',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.48,
    passed_assertions: 520,
    total_assertions: 1000,
    avg_tokens: 57800,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-05T10:00:00Z',
    started_at: '2024-12-05T10:01:00Z',
    completed_at: '2024-12-05T16:30:00Z',
  },
  {
    id: 'exp-004',
    name: 'Epoch 4 - Cluster Formation',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.55,
    passed_assertions: 590,
    total_assertions: 1000,
    avg_tokens: 52100,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-06T08:00:00Z',
    started_at: '2024-12-06T08:01:00Z',
    completed_at: '2024-12-06T14:00:00Z',
  },
  {
    id: 'exp-005',
    name: 'Epoch 5 - Solution Discovery',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.61,
    passed_assertions: 645,
    total_assertions: 1000,
    avg_tokens: 48500,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-08T09:00:00Z',
    started_at: '2024-12-08T09:01:00Z',
    completed_at: '2024-12-08T15:00:00Z',
  },
  {
    id: 'exp-006',
    name: 'Epoch 6 - Knowledge Transfer',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.67,
    passed_assertions: 705,
    total_assertions: 1000,
    avg_tokens: 44200,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-09T10:00:00Z',
    started_at: '2024-12-09T10:01:00Z',
    completed_at: '2024-12-09T16:00:00Z',
  },
  {
    id: 'exp-007',
    name: 'Epoch 7 - Efficiency Gains',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.72,
    passed_assertions: 755,
    total_assertions: 1000,
    avg_tokens: 41800,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-10T08:00:00Z',
    started_at: '2024-12-10T08:01:00Z',
    completed_at: '2024-12-10T14:00:00Z',
  },
  {
    id: 'exp-008',
    name: 'Epoch 8 - Convergence',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'completed',
    tasks_completed: 100,
    tasks_total: 100,
    success_rate: 0.78,
    passed_assertions: 820,
    total_assertions: 1000,
    avg_tokens: 38400,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-11T09:00:00Z',
    started_at: '2024-12-11T09:01:00Z',
    completed_at: '2024-12-11T15:00:00Z',
  },
  {
    id: 'exp-009',
    name: 'Epoch 9 - Current Training',
    experiment_type: 'learning_curve',
    dataset_split: 'train',
    status: 'running',
    tasks_completed: 67,
    tasks_total: 100,
    success_rate: 0.79,
    passed_assertions: 560,
    total_assertions: 670,
    avg_tokens: 37200,
    config: { task_limit: 100, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-12T08:00:00Z',
    started_at: '2024-12-12T08:01:00Z',
    completed_at: null,
  },
  {
    id: 'exp-010',
    name: 'Test Normal Evaluation',
    experiment_type: 'baseline',
    dataset_split: 'test_normal',
    status: 'pending',
    tasks_completed: 0,
    tasks_total: 50,
    success_rate: null,
    passed_assertions: 0,
    total_assertions: 0,
    avg_tokens: null,
    config: { task_limit: 50, turns_per_task: 20, checkpoint_interval: 10 },
    created_at: '2024-12-12T10:00:00Z',
    started_at: null,
    completed_at: null,
  },
];

const MOCK_TASK_RESULTS = [
  { id: 'tr1', task_id: '07b42fd_1', session_id: MOCK_SESSIONS[0].id, success: true, iterations: 5, duration_ms: 45200, test_results: { passes: ['test1', 'test2', 'test3'], failures: [], num_tests: 3 }, micro_outcomes: { solved: 3, progress: 2, stuck: 0, error: 0 } },
  { id: 'tr2', task_id: '09b0ee6_1', session_id: MOCK_SESSIONS[1].id, success: true, iterations: 4, duration_ms: 28100, test_results: { passes: ['test1', 'test2'], failures: [], num_tests: 2 }, micro_outcomes: { solved: 2, progress: 2, stuck: 0, error: 0 } },
  { id: 'tr3', task_id: '0de03ea_1', session_id: MOCK_SESSIONS[2].id, success: false, iterations: 8, duration_ms: 89400, test_results: { passes: ['test1'], failures: ['test2', 'test3'], num_tests: 3 }, micro_outcomes: { solved: 1, progress: 4, stuck: 2, error: 1 } },
  { id: 'tr4', task_id: '12abc34_1', session_id: MOCK_SESSIONS[3].id, success: true, iterations: 3, duration_ms: 18700, test_results: { passes: ['test1', 'test2'], failures: [], num_tests: 2 }, micro_outcomes: { solved: 2, progress: 1, stuck: 0, error: 0 } },
  { id: 'tr5', task_id: '34def56_1', session_id: null, success: false, iterations: 10, duration_ms: 120000, test_results: { passes: [], failures: ['test1', 'test2'], num_tests: 2 }, micro_outcomes: { solved: 0, progress: 5, stuck: 4, error: 1 } },
];

const MOCK_CLUSTERS = [
  { id: 'clst-001', label: 'API pagination and iteration patterns', turn_count: 67, success_count: 58, failure_count: 9, solutions: 4 },
  { id: 'clst-002', label: 'JSON response parsing and validation', turn_count: 45, success_count: 41, failure_count: 4, solutions: 3 },
  { id: 'clst-003', label: 'Authentication and token management', turn_count: 38, success_count: 21, failure_count: 17, solutions: 5 },
  { id: 'clst-004', label: 'File system operations', turn_count: 29, success_count: 12, failure_count: 17, solutions: 2 },
  { id: 'clst-005', label: 'Database query construction', turn_count: 24, success_count: 19, failure_count: 5, solutions: 3 },
  { id: 'clst-006', label: 'Error handling and recovery', turn_count: 21, success_count: 14, failure_count: 7, solutions: 2 },
];

const MOCK_INTELLIGENCE = {
  knowledge_gaps: [
    { cluster_id: 'clst-004', label: 'File system operations', failures: 17, successes: 12 },
    { cluster_id: 'clst-003', label: 'Authentication and token management', failures: 17, successes: 21 },
  ],
  harmful_bullets: [
    { id: 'blt-006', content: 'Always verify directory exists...', helpful: 8, harmful: 23 },
  ],
  struggling_clusters: [
    { cluster_id: 'clst-004', label: 'File system operations', turns: 29, success_rate: 41.4 },
    { cluster_id: 'clst-003', label: 'Authentication and token management', turns: 38, success_rate: 55.3 },
  ],
  recommendations: [
    'Synthesize new bullets for file system operations cluster',
    'Review and potentially archive bullet blt-006',
    'Add more constraints for authentication edge cases',
  ],
};

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ');
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit'
  });
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

function truncate(str: string, len: number): string {
  return str.length > len ? str.slice(0, len) + '...' : str;
}

function calculateEffectiveness(helpful: number, harmful: number, neutral: number): number {
  const total = helpful + harmful + neutral;
  if (total === 0) return 0;
  return helpful / total;
}

// ============================================================================
// UI COMPONENTS
// ============================================================================

function Badge({ children, variant = 'default', className = '' }: {
  children: React.ReactNode;
  variant?: 'default' | 'secondary' | 'success' | 'warning' | 'error' | 'info';
  className?: string;
}) {
  const variants = {
    default: 'bg-gray-100 text-gray-800',
    secondary: 'bg-gray-200 text-gray-700',
    success: 'bg-green-100 text-green-800',
    warning: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
    info: 'bg-blue-100 text-blue-800',
  };
  return (
    <span className={cn('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium', variants[variant], className)}>
      {children}
    </span>
  );
}

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('rounded-lg bg-white shadow', className)}>{children}</div>;
}

function CardHeader({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('flex flex-col space-y-1.5 px-5 py-4', className)}>{children}</div>;
}

function CardTitle({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <h3 className={cn('text-base font-semibold leading-none tracking-tight', className)}>{children}</h3>;
}

function CardContent({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return <div className={cn('px-5 pb-5', className)}>{children}</div>;
}

function Button({ children, variant = 'default', size = 'md', className = '', onClick, disabled, loading, type = 'button' }: {
  children: React.ReactNode;
  variant?: 'default' | 'primary' | 'secondary' | 'destructive' | 'ghost' | 'link';
  size?: 'sm' | 'md' | 'lg' | 'icon';
  className?: string;
  onClick?: () => void;
  disabled?: boolean;
  loading?: boolean;
  type?: 'button' | 'submit';
}) {
  const variants = {
    default: 'bg-gray-900 text-white hover:bg-gray-800',
    primary: 'bg-blue-600 text-white hover:bg-blue-700',
    secondary: 'bg-gray-100 text-gray-900 hover:bg-gray-200 border border-gray-200',
    destructive: 'bg-red-600 text-white hover:bg-red-700',
    ghost: 'hover:bg-gray-100 hover:text-gray-900',
    link: 'text-blue-600 underline-offset-4 hover:underline',
  };
  const sizes = {
    sm: 'h-7 px-2.5 text-xs',
    md: 'h-9 px-4 text-sm',
    lg: 'h-11 px-6 text-base',
    icon: 'h-9 w-9',
  };
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50',
        variants[variant], sizes[size], className
      )}
    >
      {loading && (
        <svg className="mr-2 h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  );
}

function Input({ className = '', ...props }: React.InputHTMLAttributes<HTMLInputElement> & { className?: string }) {
  return (
    <input
      className={cn(
        'flex h-9 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm ring-offset-white placeholder:text-gray-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50',
        className
      )}
      {...props}
    />
  );
}

function Select({ options, className = '', ...props }: {
  options: { value: string; label: string }[];
  className?: string;
} & React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        'flex h-9 w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm ring-offset-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400 focus-visible:ring-offset-2',
        className
      )}
      {...props}
    >
      {options.map(opt => (
        <option key={opt.value} value={opt.value}>{opt.label}</option>
      ))}
    </select>
  );
}

function ProgressBar({ value, variant = 'default' }: { value: number; variant?: 'default' | 'success' | 'error' }) {
  const colors = {
    default: 'bg-blue-500',
    success: 'bg-green-500',
    error: 'bg-red-500',
  };
  return (
    <div className="h-2 w-full rounded-full bg-gray-200">
      <div
        className={cn('h-full rounded-full transition-all', colors[variant])}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

function MicroOutcomeBadge({ outcome }: { outcome?: string }) {
  const styles: Record<string, string> = {
    solved: 'bg-green-100 text-green-800',
    progress: 'bg-blue-100 text-blue-800',
    stuck: 'bg-yellow-100 text-yellow-800',
    error: 'bg-red-100 text-red-800',
  };
  if (!outcome) return null;
  return <Badge className={styles[outcome] || styles.progress}>{outcome}</Badge>;
}

function PolarityBadge({ polarity }: { polarity: string }) {
  const styles: Record<string, string> = {
    do: 'bg-green-100 text-green-800',
    dont: 'bg-red-100 text-red-800',
    know: 'bg-blue-100 text-blue-800',
  };
  return <Badge className={styles[polarity] || 'bg-gray-100 text-gray-800'}>{polarity}</Badge>;
}

// ============================================================================
// LAYOUT COMPONENTS
// ============================================================================

function Sidebar() {
  const location = useLocation();

  const navItems = [
    { path: '/', icon: MessageSquare, label: 'Chat', color: 'blue' },
  ];

  const insightItems = [
    { path: '/sessions', icon: List, label: 'Sessions', color: 'blue' },
    { path: '/library', icon: BookOpen, label: 'Library', color: 'purple' },
    { path: '/knowledge-graph', icon: Network, label: 'Knowledge Graph', color: 'green' },
  ];

  const learningItems = [
    { path: '/learning-loop', icon: Brain, label: 'Learning Loop', color: 'amber' },
    { path: '/system', icon: Settings, label: 'System', color: 'rose' },
    { path: '/evaluation', icon: FlaskConical, label: 'Evaluation', color: 'teal' },
  ];

  const colorMap: Record<string, { active: string; icon: string }> = {
    blue: { active: 'bg-blue-50 text-blue-700 border-blue-200', icon: 'text-blue-500' },
    purple: { active: 'bg-purple-50 text-purple-700 border-purple-200', icon: 'text-purple-500' },
    green: { active: 'bg-green-50 text-green-700 border-green-200', icon: 'text-green-500' },
    amber: { active: 'bg-amber-50 text-amber-700 border-amber-200', icon: 'text-amber-500' },
    rose: { active: 'bg-rose-50 text-rose-700 border-rose-200', icon: 'text-rose-500' },
    teal: { active: 'bg-teal-50 text-teal-700 border-teal-200', icon: 'text-teal-500' },
  };

  const NavItem = ({ item }: { item: typeof navItems[0] }) => {
    const isActive = location.pathname === item.path ||
      (item.path !== '/' && location.pathname.startsWith(item.path));
    const Icon = item.icon;
    const colors = colorMap[item.color];

    return (
      <Link
        to={item.path}
        className={cn(
          'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all',
          isActive ? `${colors.active} border` : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
        )}
      >
        <Icon className={cn('h-4 w-4', isActive ? colors.icon : 'text-gray-400')} />
        <span>{item.label}</span>
      </Link>
    );
  };

  return (
    <aside className="flex h-screen w-64 flex-col border-r bg-gradient-to-b from-white to-gray-50/50">
      {/* Header */}
      <div className="border-b px-4 py-5">
        <Link to="/" className="block">
          <div className="text-3xl font-bold tracking-tight text-gray-900">ALEC</div>
          <div className="text-sm text-gray-500 leading-tight mt-0.5">
            Agent Learning + Evolving Context
          </div>
        </Link>
      </div>

      {/* Navigation */}
      <div className="flex-1 overflow-y-auto py-4 px-3">
        {/* Chat */}
        <div className="mb-6">
          <div className="flex items-center gap-2">
            <div className="flex-1"><NavItem item={navItems[0]} /></div>
            <button className="p-2 rounded-lg bg-blue-50 text-blue-500 hover:bg-blue-100 transition-colors">
              <Plus className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Insights */}
        <div className="mb-6">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 px-3 mb-2">Insights</div>
          <div className="space-y-1">
            {insightItems.map(item => <NavItem key={item.path} item={item} />)}
          </div>
        </div>

        {/* Learning */}
        <div className="mb-6">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-gray-400 px-3 mb-2">Learning</div>
          <div className="space-y-1">
            {learningItems.map(item => <NavItem key={item.path} item={item} />)}
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="border-t px-4 py-3">
        <div className="flex items-center justify-between text-xs text-gray-500">
          <span>v3.0</span>
          <span className="flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Connected
          </span>
        </div>
      </div>
    </aside>
  );
}

function Layout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl px-8 py-8">
          {children}
        </div>
      </main>
    </div>
  );
}

// ============================================================================
// PAGE COMPONENTS
// ============================================================================

function ChatPage() {
  const [input, setInput] = useState('');
  const [messages] = useState([
    { id: '1', role: 'user', content: 'Help me get all songs from my Spotify liked songs playlist' },
    { id: '2', role: 'assistant', content: `I'll help you retrieve all songs from your liked songs. Let me use the Spotify API to fetch this data.\n\n\`\`\`python\nliked_songs = []\noffset = 0\nwhile True:\n    batch = get_liked_songs(offset=offset, limit=50)\n    liked_songs.extend(batch)\n    if len(batch) < 50:\n        break\n    offset += 50\nprint(f"Found {len(liked_songs)} liked songs")\n\`\`\`\n\nThis handles pagination correctly using the offset parameter. Found 347 liked songs.` },
    { id: '3', role: 'user', content: 'Now filter to only songs with rating above 4' },
    { id: '4', role: 'assistant', content: `I'll filter the songs by rating. Note that the standard API doesn't return ratings directly - I need to check the private API.\n\n\`\`\`python\nhigh_rated = []\nfor song in liked_songs:\n    details = show_song_privates(song.id)\n    if details.rating > 4:\n        high_rated.append(song)\nprint(f"Found {len(high_rated)} songs rated above 4")\n\`\`\`\n\nFound 47 songs rated above 4 stars.` },
  ]);

  return (
    <Layout>
      <div className="h-[calc(100vh-8rem)] flex flex-col">
        {/* Messages */}
        <div className="flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto space-y-6 pb-4">
            {messages.length === 0 ? (
              <div className="flex items-center justify-center min-h-[60vh]">
                <div className="text-center space-y-4">
                  <h1 className="text-5xl font-semibold text-gray-900">ALEC</h1>
                  <p className="text-xl text-gray-500">How can I help you today?</p>
                </div>
              </div>
            ) : (
              messages.map((message) => (
                <div key={message.id} className="flex flex-col">
                  <div className="flex items-start gap-4">
                    <div className={cn(
                      'flex-shrink-0 text-sm font-semibold text-gray-500 min-w-[60px]',
                      message.role === 'user' ? 'text-right' : ''
                    )}>
                      {message.role === 'user' ? 'You' : 'ALEC'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className={cn(
                        'rounded-lg px-4 py-3',
                        message.role === 'user'
                          ? 'bg-gray-100 border-l-2 border-blue-500'
                          : 'bg-gray-50 border-l-2 border-gray-300'
                      )}>
                        <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
                          {message.content}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Input */}
        <div className="border-t bg-white/80 backdrop-blur">
          <div className="max-w-4xl mx-auto px-4 py-4">
            <form onSubmit={(e) => { e.preventDefault(); }}>
              <div className="relative">
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Type your message here..."
                  className="w-full rounded-lg border border-gray-200 bg-white px-4 py-3 pr-12 text-sm ring-offset-white placeholder:text-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
                />
                <Button
                  type="submit"
                  size="icon"
                  className="absolute right-2 top-1/2 -translate-y-1/2 h-8 w-8"
                  disabled={!input.trim()}
                >
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </Layout>
  );
}

function SessionsPage() {
  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Sessions</h1>
          <p className="text-gray-500">View and analyze chat sessions</p>
        </div>

        <Card>
          <CardContent className="p-4">
            <div className="flex gap-4">
              <Input placeholder="Search sessions..." className="max-w-xs" />
              <Select
                options={[
                  { value: '', label: 'All domains' },
                  { value: 'spotify', label: 'Spotify' },
                  { value: 'weather', label: 'Weather' },
                  { value: 'filesystem', label: 'Filesystem' },
                ]}
                className="w-40"
              />
              <Select
                options={[
                  { value: '', label: 'All statuses' },
                  { value: 'active', label: 'Active' },
                  { value: 'completed', label: 'Completed' },
                ]}
                className="w-40"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Session</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Domain</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Messages</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Outcomes</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {MOCK_SESSIONS.map(session => (
                  <tr key={session.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link to={`/sessions/${session.id}`} className="font-medium text-blue-600 hover:underline">
                        {session.title || session.id.slice(0, 8)}
                      </Link>
                      <div className="text-xs text-gray-400 font-mono">{session.id.slice(0, 8)}...</div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge>{session.domain}</Badge>
                    </td>
                    <td className="px-4 py-3 text-sm">{session.message_count}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1 flex-wrap">
                        {session.micro_outcomes.solved > 0 && (
                          <Badge variant="success">{session.micro_outcomes.solved} solved</Badge>
                        )}
                        {session.micro_outcomes.progress > 0 && (
                          <Badge variant="info">{session.micro_outcomes.progress} progress</Badge>
                        )}
                        {session.micro_outcomes.stuck > 0 && (
                          <Badge variant="warning">{session.micro_outcomes.stuck} stuck</Badge>
                        )}
                        {session.micro_outcomes.error > 0 && (
                          <Badge variant="error">{session.micro_outcomes.error} error</Badge>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <Badge variant={session.status === 'completed' ? (session.success ? 'success' : 'error') : 'info'}>
                        {session.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatRelativeTime(session.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </Layout>
  );
}

function SessionDetailPage() {
  const { sessionId } = useParams();
  const session = MOCK_SESSIONS.find(s => s.id === sessionId) || MOCK_SESSIONS[0];
  const [expandedTurns, setExpandedTurns] = useState<Set<string>>(new Set());

  const toggleTurn = (turnId: string) => {
    setExpandedTurns(prev => {
      const next = new Set(prev);
      if (next.has(turnId)) next.delete(turnId);
      else next.add(turnId);
      return next;
    });
  };

  return (
    <Layout>
      <div className="space-y-6">
        {/* Back link */}
        <Link to="/sessions">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeft className="h-4 w-4" />
            Back to Sessions
          </Button>
        </Link>

        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold">{session.title || `Session ${session.id.slice(0, 8)}`}</h1>
            <p className="mt-1 text-sm text-gray-500 font-mono">{session.id}</p>
          </div>
          <Badge variant={session.status === 'completed' ? (session.success ? 'success' : 'error') : 'info'}>
            {session.status}
          </Badge>
        </div>

        {/* Metadata */}
        <div className="flex flex-wrap gap-6 text-sm">
          <div><span className="text-gray-500">Domain:</span> <span className="font-medium">{session.domain}</span></div>
          <div><span className="text-gray-500">Messages:</span> <span className="font-medium">{session.message_count}</span></div>
          <div><span className="text-gray-500">Created:</span> <span className="font-medium">{formatDate(session.created_at)}</span></div>
        </div>

        {/* Stats */}
        <Card>
          <CardHeader><CardTitle>Session Statistics</CardTitle></CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-1">
              <p className="text-2xl font-bold">{MOCK_TURNS.length}</p>
              <p className="text-sm text-gray-500">Total Turns</p>
            </div>
            <div className="space-y-1">
              <div className="flex gap-2 text-sm">
                <span className="text-green-600">{session.micro_outcomes.solved} solved</span>
                <span className="text-blue-600">{session.micro_outcomes.progress} progress</span>
              </div>
              <div className="flex gap-2 text-sm">
                <span className="text-yellow-600">{session.micro_outcomes.stuck} stuck</span>
                <span className="text-red-600">{session.micro_outcomes.error} error</span>
              </div>
              <p className="text-sm text-gray-500">Micro-outcomes</p>
            </div>
            <div className="space-y-1">
              <p className="text-2xl font-bold">7</p>
              <p className="text-sm text-gray-500">Bullets Shown</p>
            </div>
            <div className="space-y-1">
              <div className="flex gap-2">
                <span className="text-lg font-bold text-green-600">+4</span>
                <span className="text-lg font-bold text-red-600">-1</span>
              </div>
              <p className="text-sm text-gray-500">Helped / Harmed</p>
            </div>
          </CardContent>
        </Card>

        {/* Timeline */}
        <div>
          <h2 className="mb-4 text-lg font-semibold">Conversation Timeline</h2>
          <div className="space-y-4">
            {MOCK_TURNS.map((turn) => {
              const isExpanded = expandedTurns.has(turn.turn_id);
              return (
                <Card key={turn.turn_id} className="overflow-hidden">
                  <div
                    className="cursor-pointer p-4"
                    onClick={() => toggleTurn(turn.turn_id)}
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-100 text-sm font-medium text-blue-700">
                          {turn.turn_number}
                        </div>
                        <MicroOutcomeBadge outcome={turn.micro_outcome} />
                      </div>
                      <Button variant="ghost" size="icon" className="shrink-0">
                        <ChevronRight className={cn('h-4 w-4 transition-transform', isExpanded && 'rotate-90')} />
                      </Button>
                    </div>
                    <div className="mt-2 space-y-1">
                      <p className="text-sm text-gray-600">
                        <span className="font-medium">User:</span> {truncate(turn.user_message, 100)}
                      </p>
                      {!isExpanded && (
                        <p className="text-sm text-gray-500">
                          <span className="font-medium">Assistant:</span> {truncate(turn.assistant_response, 100)}
                        </p>
                      )}
                    </div>
                  </div>

                  {isExpanded && (
                    <CardContent className="border-t pt-4">
                      <div className="mb-4">
                        <h4 className="mb-1 text-xs font-medium uppercase text-gray-500">User Message</h4>
                        <div className="whitespace-pre-wrap rounded-lg bg-gray-50 p-3 text-sm">
                          {turn.user_message}
                        </div>
                      </div>
                      <div className="mb-4">
                        <h4 className="mb-1 text-xs font-medium uppercase text-gray-500">Assistant Response</h4>
                        <div className="whitespace-pre-wrap rounded-lg bg-blue-50 p-3 text-sm">
                          {turn.assistant_response}
                        </div>
                      </div>
                      {turn.sub_task && (
                        <div className="mb-4">
                          <h4 className="mb-1 text-xs font-medium uppercase text-gray-500">Sub-task</h4>
                          <p className="text-sm">{turn.sub_task}</p>
                        </div>
                      )}
                      <div>
                        <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">Bullet Attribution</h4>
                        <div className="flex flex-wrap gap-2">
                          {turn.bullets_shown.length === 0 ? (
                            <span className="text-sm text-gray-400">No bullets shown</span>
                          ) : (
                            <>
                              {turn.bullets_helped.map(id => (
                                <Link key={id} to={`/library/${id}`}>
                                  <Badge variant="success" className="cursor-pointer hover:opacity-80">
                                    +{id.slice(0, 7)}
                                  </Badge>
                                </Link>
                              ))}
                              {turn.bullets_harmed.map(id => (
                                <Link key={id} to={`/library/${id}`}>
                                  <Badge variant="error" className="cursor-pointer hover:opacity-80">
                                    -{id.slice(0, 7)}
                                  </Badge>
                                </Link>
                              ))}
                              {turn.bullets_shown
                                .filter(id => !turn.bullets_helped.includes(id) && !turn.bullets_harmed.includes(id))
                                .map(id => (
                                  <Link key={id} to={`/library/${id}`}>
                                    <Badge className="cursor-pointer hover:opacity-80">{id.slice(0, 7)}</Badge>
                                  </Link>
                                ))}
                            </>
                          )}
                        </div>
                      </div>
                      <div className="mt-4 text-xs text-gray-500">{formatRelativeTime(turn.created_at)}</div>
                    </CardContent>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      </div>
    </Layout>
  );
}

function LibraryPage() {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const toggleSelect = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Bullet Library</h1>
          <p className="text-gray-500">Manage knowledge bullets ({MOCK_BULLETS.length} total)</p>
        </div>

        <Card>
          <CardContent className="p-4">
            <div className="flex gap-4 flex-wrap">
              <Input placeholder="Search bullets..." className="max-w-xs" />
              <Select
                options={[
                  { value: '', label: 'All types' },
                  { value: 'do', label: 'Do' },
                  { value: 'dont', label: "Don't" },
                  { value: 'know', label: 'Know' },
                ]}
                className="w-32"
              />
              <Select
                options={[
                  { value: '', label: 'All statuses' },
                  { value: 'active', label: 'Active' },
                  { value: 'candidate', label: 'Candidate' },
                  { value: 'archived', label: 'Archived' },
                ]}
                className="w-36"
              />
              <Select
                options={[
                  { value: '', label: 'All categories' },
                  { value: 'solutions', label: 'Solutions' },
                  { value: 'constraints', label: 'Constraints' },
                  { value: 'meta_prompts', label: 'Meta Prompts' },
                  { value: 'cheat_sheets', label: 'Cheat Sheets' },
                ]}
                className="w-40"
              />
            </div>
          </CardContent>
        </Card>

        {selectedIds.size > 0 && (
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <span className="text-sm text-gray-500">{selectedIds.size} selected</span>
              <Button variant="secondary" size="sm">Activate</Button>
              <Button variant="secondary" size="sm">Archive</Button>
              <Button variant="ghost" size="sm" onClick={() => setSelectedIds(new Set())}>Clear</Button>
            </CardContent>
          </Card>
        )}

        <Card>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="w-12 px-4 py-3">
                    <input type="checkbox" className="h-4 w-4 rounded border-gray-300" />
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Situation</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Assertion</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Effectiveness</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {MOCK_BULLETS.map(bullet => {
                  const eff = calculateEffectiveness(bullet.helpful_count, bullet.harmful_count, bullet.neutral_count);
                  return (
                    <tr key={bullet.id} className={cn('hover:bg-gray-50', selectedIds.has(bullet.id) && 'bg-blue-50')}>
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={selectedIds.has(bullet.id)}
                          onChange={() => toggleSelect(bullet.id)}
                          className="h-4 w-4 rounded border-gray-300"
                        />
                      </td>
                      <td className="px-4 py-3">
                        <Link to={`/library/${bullet.id}`} className="font-medium text-blue-600 hover:underline">
                          {truncate(bullet.situation, 50)}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-600 max-w-xs">
                        {truncate(bullet.assertion, 60)}
                      </td>
                      <td className="px-4 py-3"><PolarityBadge polarity={bullet.polarity} /></td>
                      <td className="px-4 py-3">
                        <Badge variant={bullet.status === 'active' ? 'success' : bullet.status === 'archived' ? 'error' : 'warning'}>
                          {bullet.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <span className={cn(
                            'font-medium',
                            eff >= 0.7 ? 'text-green-600' : eff >= 0.4 ? 'text-yellow-600' : 'text-red-600'
                          )}>
                            {(eff * 100).toFixed(0)}%
                          </span>
                          <span className="text-xs text-gray-500">
                            ({bullet.helpful_count}+/{bullet.harmful_count}-)
                          </span>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500">{formatRelativeTime(bullet.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="border-t p-4 flex items-center justify-between text-sm text-gray-500">
            <span>Showing 1-{MOCK_BULLETS.length} of {MOCK_BULLETS.length}</span>
            <div className="flex gap-2">
              <Button variant="secondary" size="sm" disabled>Previous</Button>
              <Button variant="secondary" size="sm" disabled>Next</Button>
            </div>
          </div>
        </Card>
      </div>
    </Layout>
  );
}

function BulletDetailPage() {
  const { bulletId } = useParams();
  const bullet = MOCK_BULLETS.find(b => b.id === bulletId) || MOCK_BULLETS[0];
  const eff = calculateEffectiveness(bullet.helpful_count, bullet.harmful_count, bullet.neutral_count);

  return (
    <Layout>
      <div className="space-y-6">
        <Link to="/library">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeft className="h-4 w-4" />
            Back to Library
          </Button>
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">Bullet Details</h1>
              <Badge variant={bullet.status === 'active' ? 'success' : bullet.status === 'archived' ? 'error' : 'warning'}>
                {bullet.status}
              </Badge>
            </div>
            <p className="mt-1 text-sm text-gray-500 font-mono">{bullet.id}</p>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" size="sm">Edit</Button>
            <Button variant="destructive" size="sm">Archive</Button>
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader><CardTitle>Content</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <div className="text-xs font-medium uppercase text-gray-500 mb-1">Situation</div>
                <div className="text-sm bg-gray-50 p-3 rounded-lg">{bullet.situation}</div>
              </div>
              <div>
                <div className="text-xs font-medium uppercase text-gray-500 mb-1">Assertion</div>
                <div className="text-sm bg-gray-50 p-3 rounded-lg">{bullet.assertion}</div>
              </div>
              <div className="flex gap-4">
                <div>
                  <div className="text-xs font-medium uppercase text-gray-500 mb-1">Category</div>
                  <Badge>{bullet.category}</Badge>
                </div>
                <div>
                  <div className="text-xs font-medium uppercase text-gray-500 mb-1">Polarity</div>
                  <PolarityBadge polarity={bullet.polarity} />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle>Effectiveness</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="text-center">
                <span className={cn(
                  'text-4xl font-bold',
                  eff >= 0.7 ? 'text-green-600' : eff >= 0.4 ? 'text-yellow-600' : 'text-red-600'
                )}>
                  {(eff * 100).toFixed(1)}%
                </span>
                <p className="text-sm text-gray-500">Overall Effectiveness</p>
              </div>
              <div className="grid grid-cols-3 gap-4 text-center">
                <div className="bg-green-50 p-3 rounded-lg">
                  <div className="text-xl font-bold text-green-600">{bullet.helpful_count}</div>
                  <div className="text-xs text-gray-500">Helpful</div>
                </div>
                <div className="bg-red-50 p-3 rounded-lg">
                  <div className="text-xl font-bold text-red-600">{bullet.harmful_count}</div>
                  <div className="text-xs text-gray-500">Harmful</div>
                </div>
                <div className="bg-gray-50 p-3 rounded-lg">
                  <div className="text-xl font-bold text-gray-600">{bullet.neutral_count}</div>
                  <div className="text-xs text-gray-500">Neutral</div>
                </div>
              </div>
              <div className="border-t pt-4">
                <div className="text-xs font-medium uppercase text-gray-500 mb-2">Evidence</div>
                <p className="text-sm">
                  <span className="font-medium">{bullet.evidence_count}</span> confirmations from similar situations
                </p>
              </div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Recent Usage</CardTitle></CardHeader>
          <CardContent>
            <div className="space-y-2">
              {MOCK_SESSIONS.slice(0, 3).map(session => (
                <div key={session.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <Link to={`/sessions/${session.id}`} className="text-sm text-blue-600 hover:underline">
                    {session.title}
                  </Link>
                  <span className="text-xs text-gray-500">{formatRelativeTime(session.created_at)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>
    </Layout>
  );
}

function KnowledgeGraphPage() {
  return (
    <Layout>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold">Knowledge Graph</h1>
          <p className="text-gray-500">Visualize problem clusters and their solutions</p>
        </div>

        <div className="grid grid-cols-3 gap-4">
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-blue-600">{MOCK_CLUSTERS.length}</div>
              <div className="text-sm text-gray-500">Problem Clusters</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-green-600">19</div>
              <div className="text-sm text-gray-500">solved_by Edges</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6 text-center">
              <div className="text-3xl font-bold text-red-600">6</div>
              <div className="text-sm text-gray-500">caused_failure Edges</div>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader><CardTitle>Problem Clusters</CardTitle></CardHeader>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Label</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Turns</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Success Rate</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Solutions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {MOCK_CLUSTERS.map(cluster => {
                  const rate = (cluster.success_count / cluster.turn_count) * 100;
                  return (
                    <tr key={cluster.id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-medium">{cluster.label}</td>
                      <td className="px-4 py-3 text-sm text-gray-600">{cluster.turn_count}</td>
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
                            <div
                              className={cn('h-full', rate >= 70 ? 'bg-green-500' : rate >= 50 ? 'bg-yellow-500' : 'bg-red-500')}
                              style={{ width: `${rate}%` }}
                            />
                          </div>
                          <Badge variant={rate >= 70 ? 'success' : rate >= 50 ? 'warning' : 'error'}>
                            {rate.toFixed(1)}%
                          </Badge>
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">{cluster.solutions} bullets</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </Layout>
  );
}

function LearningLoopPage() {
  return (
    <Layout>
      <div className="space-y-10 pb-12">
        <div className="border-b pb-6">
          <h1 className="text-3xl font-bold">Learning Loop</h1>
          <p className="mt-3 text-lg text-gray-600">
            Event-driven learning system that observes sessions, extracts patterns, and improves responses through Thompson Sampling.
          </p>
        </div>

        {/* Architecture */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">System Overview</h2>
          <Card>
            <CardContent className="p-6">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <MermaidDiagram chart={OVERVIEW_DIAGRAM} />
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Services */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Learning Loop Services</h2>
          <div className="space-y-4">
            <Collapsible title="ADVISOR" icon="A" badge="Selection" badgeColor="amber">
              <div className="space-y-4">
                <p className="text-gray-600">Selects bullets for each turn using Thompson Sampling with cluster-aware filtering.</p>
                <div className="space-y-2">
                  {['Vector search on situation_embedding (threshold 0.50)', 'Retrieves cluster solutions via solved_by edges', 'Filters harmful bullets via caused_failure edges', 'Scores: similarity × thompson_sample × age_decay'].map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-green-500" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={ADVISOR_DIAGRAM} />
                </div>
              </div>
            </Collapsible>

            <Collapsible title="REFLECTOR" icon="R" badge="Feedback Owner" badgeColor="purple">
              <div className="space-y-4">
                <p className="text-gray-600">Owns the entire feedback loop: turn analysis, attribution, counters, and AKU extraction.</p>
                <div className="space-y-2">
                  {['Analyzes turns for micro-outcomes on session end', 'Updates helpful/harmful/neutral counters', 'Creates caused_failure edges for harmful bullets', 'Extracts AKUs from stuck→recovery patterns'].map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-green-500" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={REFLECTOR_DIAGRAM} />
                </div>
              </div>
            </Collapsible>

            <Collapsible title="CURATOR" icon="C" badge="Quality Gate" badgeColor="green">
              <div className="space-y-4">
                <p className="text-gray-600">Single quality gate for all AKU sources with embedding-based deduplication.</p>
                <div className="space-y-2">
                  {['Consumes aku.proposed from REFLECTOR and STRATEGIST', 'Dedup on assertion_embedding (0.70/0.90 thresholds)', 'Two-space storage: situation + assertion embeddings', 'Emits bullet.accepted or bullet.merged'].map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-green-500" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={CURATOR_DIAGRAM} />
                </div>
              </div>
            </Collapsible>

            <Collapsible title="CLUSTERER" icon="C" badge="Graph Manager" badgeColor="blue">
              <div className="space-y-4">
                <p className="text-gray-600">Assigns turns to clusters and maintains the knowledge graph.</p>
                <div className="space-y-2">
                  {['Assigns turns to problem_clusters by embedding similarity', 'Creates solved_by edges for helpful bullets', 'Updates cluster stats (turn_count, success_count)', 'Status transitions: candidate→active→archived'].map((f, i) => (
                    <div key={i} className="flex items-start gap-2 text-sm text-gray-600">
                      <Check className="h-4 w-4 mt-0.5 flex-shrink-0 text-green-500" />
                      <span>{f}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={CLUSTERER_DIAGRAM} />
                </div>
              </div>
            </Collapsible>
          </div>
        </section>

        {/* Strategic Agents */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Strategic Agents</h2>
          <div className="space-y-4">
            <Collapsible title="LIBRARIAN" icon="L" badge="Passive / Analytical" badgeColor="slate">
              <div className="space-y-4">
                <p className="text-gray-600">Analyzes the library for gaps and hygiene issues.</p>
                <ul className="space-y-2 text-sm text-gray-600">
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-amber-500 flex-shrink-0" />
                    <span><strong>Gap detection:</strong> Clusters with failures but no solved_by edges</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-yellow-500 flex-shrink-0" />
                    <span><strong>Struggling clusters:</strong> Has solutions but poor success rate (&lt;50%)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-red-500 flex-shrink-0" />
                    <span><strong>Auto-archive:</strong> Bullets where harmful &gt; helpful</span>
                  </li>
                </ul>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={LIBRARIAN_DIAGRAM} />
                </div>
              </div>
            </Collapsible>

            <Collapsible title="STRATEGIST" icon="S" badge="Active / Strategic" badgeColor="red">
              <div className="space-y-4">
                <p className="text-gray-600">Synthesizes new bullets to fill knowledge gaps.</p>
                <ul className="space-y-2 text-sm text-gray-600">
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-blue-500 flex-shrink-0" />
                    <span>Consumes <code className="text-xs bg-gray-100 px-1 rounded">library.gap.detected</code> and <code className="text-xs bg-gray-100 px-1 rounded">library.cluster.struggling</code></span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-green-500 flex-shrink-0" />
                    <span><strong>Pre-synthesis dedup:</strong> Checks for similar bullets before LLM call</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-purple-500 flex-shrink-0" />
                    <span>Emits <code className="text-xs bg-gray-100 px-1 rounded">aku.proposed</code> → flows through CURATOR</span>
                  </li>
                </ul>
                <div className="rounded-lg border bg-gray-50 p-4 mt-4">
                  <MermaidDiagram chart={STRATEGIST_DIAGRAM} />
                </div>
              </div>
            </Collapsible>
          </div>
        </section>

        {/* Thompson Sampling */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Thompson Sampling Formula</h2>
          <Card>
            <CardContent className="p-6">
              <div className="rounded-lg bg-gray-900 p-6 font-mono text-sm text-gray-100">
                <div className="text-green-400">// Bullet selection formula</div>
                <div className="mt-2">
                  <span className="text-purple-400">final_score</span> = <span className="text-blue-400">similarity</span> &times; <span className="text-yellow-400">thompson_sample</span> &times; <span className="text-orange-400">age_decay</span>
                </div>
                <div className="mt-4 border-t border-gray-700 pt-4 text-gray-400">
                  <div>alpha = helpful_count + 1</div>
                  <div>beta = harmful_count + 0.2 &times; neutral_count + 1</div>
                  <div className="mt-2"><span className="text-yellow-400">thompson_sample</span> = random.beta(alpha, beta)</div>
                  <div><span className="text-orange-400">age_decay</span> = exp(-days &times; 0.005) <span className="text-gray-500">// 0.5% daily</span></div>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Micro-Outcomes */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Micro-Outcomes</h2>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              { name: 'solved', desc: 'Task completed successfully', color: 'green' },
              { name: 'progress', desc: 'Moving forward on task', color: 'blue' },
              { name: 'stuck', desc: 'Unable to make progress', color: 'yellow' },
              { name: 'error', desc: 'Exception or failure occurred', color: 'red' },
            ].map(o => (
              <div key={o.name} className={`rounded-xl border-2 border-${o.color}-200 bg-${o.color}-50 p-5 text-center`}>
                <span className={`text-2xl font-bold text-${o.color}-600`}>{o.name}</span>
                <p className={`mt-2 text-sm text-${o.color}-600/80`}>{o.desc}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </Layout>
  );
}

function SystemPage() {
  return (
    <Layout>
      <div className="space-y-10 pb-12">
        <div className="border-b pb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-3xl font-bold">System Dashboard</h1>
              <p className="mt-3 text-lg text-gray-600">Monitor health, manage learning data, and view intelligence insights.</p>
            </div>
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-green-50 text-green-600 text-sm">
              <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
              System Healthy
            </div>
          </div>
          <div className="mt-4 flex gap-2">
            <Link to="/learning-loop"><Button variant="secondary" size="sm">Learning Loop Docs</Button></Link>
            <Link to="/evaluation"><Button variant="secondary" size="sm">Evaluation</Button></Link>
            <Link to="/library"><Button variant="secondary" size="sm">Bullet Library</Button></Link>
            <Link to="/knowledge-graph"><Button variant="secondary" size="sm">Knowledge Graph</Button></Link>
          </div>
        </div>

        {/* Stats */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Overview</h2>
          <div className="grid gap-4 md:grid-cols-4">
            {[
              { label: 'Total Sessions', value: MOCK_SESSIONS.length, sub: `${MOCK_SESSIONS.filter(s => s.success).length} successful`, color: 'blue', icon: Database },
              { label: 'Total Bullets', value: MOCK_BULLETS.length, sub: `${MOCK_BULLETS.filter(b => b.status === 'active').length} active`, color: 'purple', icon: BookOpen },
              { label: 'Clusters', value: MOCK_CLUSTERS.length, sub: `${MOCK_CLUSTERS.length} active`, color: 'green', icon: Network },
              { label: 'Graph Edges', value: 25, sub: '19 solved_by', color: 'amber', icon: Zap },
            ].map(stat => (
              <Card key={stat.label}>
                <CardContent className="pt-6">
                  <div className="flex items-center gap-4">
                    <div className={`p-3 rounded-lg bg-${stat.color}-100`}>
                      <stat.icon className={`h-6 w-6 text-${stat.color}-600`} />
                    </div>
                    <div>
                      <div className={`text-2xl font-bold text-${stat.color}-600`}>{stat.value}</div>
                      <div className="text-sm text-gray-500">{stat.label}</div>
                      <div className="text-xs text-gray-400">{stat.sub}</div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        {/* Learning Stats */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Learning Statistics</h2>
          <Card>
            <CardContent className="py-6">
              <div className="grid grid-cols-4 gap-6">
                <div className="text-center">
                  <div className="text-3xl font-bold text-green-600">68.4%</div>
                  <div className="text-sm text-gray-500">Session Success Rate</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-blue-600">72.1%</div>
                  <div className="text-sm text-gray-500">Bullet Effectiveness</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-purple-600">4.2</div>
                  <div className="text-sm text-gray-500">Avg Bullets/Turn</div>
                </div>
                <div className="text-center">
                  <div className="text-3xl font-bold text-amber-600">85.3%</div>
                  <div className="text-sm text-gray-500">Attribution Coverage</div>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Intelligence */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Intelligence Analysis</h2>
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CardTitle>LIBRARIAN + STRATEGIST</CardTitle>
                  <Badge variant="info">Analysis</Badge>
                </div>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm">Synthesize Gaps</Button>
                  <Button size="sm">Run Analysis</Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid grid-cols-4 gap-4">
                <div className="rounded-lg bg-amber-50 p-4 text-center">
                  <div className="text-2xl font-bold text-amber-600">{MOCK_INTELLIGENCE.knowledge_gaps.length}</div>
                  <div className="text-sm font-medium text-gray-700">Knowledge Gaps</div>
                  <div className="text-xs text-gray-500">Clusters with no solutions</div>
                </div>
                <div className="rounded-lg bg-red-50 p-4 text-center">
                  <div className="text-2xl font-bold text-red-600">{MOCK_INTELLIGENCE.harmful_bullets.length}</div>
                  <div className="text-sm font-medium text-gray-700">Harmful Bullets</div>
                  <div className="text-xs text-gray-500">More harm than help</div>
                </div>
                <div className="rounded-lg bg-yellow-50 p-4 text-center">
                  <div className="text-2xl font-bold text-yellow-600">{MOCK_INTELLIGENCE.struggling_clusters.length}</div>
                  <div className="text-sm font-medium text-gray-700">Struggling Clusters</div>
                  <div className="text-xs text-gray-500">Poor success rates</div>
                </div>
                <div className="rounded-lg bg-green-50 p-4 text-center">
                  <div className="text-2xl font-bold text-green-600">{MOCK_INTELLIGENCE.recommendations.length}</div>
                  <div className="text-sm font-medium text-gray-700">Recommendations</div>
                  <div className="text-xs text-gray-500">Actionable insights</div>
                </div>
              </div>

              {/* Knowledge Gaps */}
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <h4 className="flex items-center gap-2 text-sm font-medium text-amber-700 mb-3">
                  <AlertTriangle className="h-4 w-4" />
                  Knowledge Gaps (No Solutions)
                </h4>
                <div className="space-y-2">
                  {MOCK_INTELLIGENCE.knowledge_gaps.map(gap => (
                    <div key={gap.cluster_id} className="flex items-center justify-between rounded bg-white/60 px-3 py-2 text-sm">
                      <span className="text-gray-700">{gap.label}</span>
                      <div className="flex items-center gap-2">
                        <Badge variant="error">{gap.failures} failures</Badge>
                        <Badge variant="success">{gap.successes} successes</Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Struggling Clusters */}
              <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4">
                <h4 className="flex items-center gap-2 text-sm font-medium text-yellow-700 mb-3">
                  <BarChart3 className="h-4 w-4" />
                  Struggling Clusters (Low Success Rate)
                </h4>
                <div className="space-y-2">
                  {MOCK_INTELLIGENCE.struggling_clusters.map(cluster => (
                    <div key={cluster.cluster_id} className="flex items-center justify-between rounded bg-white/60 px-3 py-2 text-sm">
                      <span className="text-gray-700">{cluster.label}</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-gray-500">{cluster.turns} turns</span>
                        <Badge variant={cluster.success_rate >= 50 ? 'warning' : 'error'}>
                          {cluster.success_rate.toFixed(1)}%
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </section>

        {/* Reset Controls */}
        <section>
          <h2 className="mb-6 text-xl font-semibold">Administrative Controls</h2>
          <Card>
            <CardContent className="py-6">
              <div className="grid grid-cols-2 gap-4">
                <div className="border rounded-lg p-4">
                  <h3 className="font-medium mb-2">Reset Learning Data</h3>
                  <p className="text-sm text-gray-500 mb-3">Clear sessions, counters, and evaluations</p>
                  <Button variant="destructive" size="sm">Reset All Data</Button>
                </div>
                <div className="border rounded-lg p-4">
                  <h3 className="font-medium mb-2">Reset Bullet Counters</h3>
                  <p className="text-sm text-gray-500 mb-3">Reset effectiveness counters only</p>
                  <Button variant="secondary" size="sm">Reset Counters</Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </section>
      </div>
    </Layout>
  );
}

function EvaluationPage() {
  const [trendsExpanded, setTrendsExpanded] = useState(true);
  const [timeWindow, setTimeWindow] = useState('all');
  const [enabledMetrics, setEnabledMetrics] = useState({ success: true, assertion: true, tokens: true });

  // Transform experiments to chart data
  const completedExps = MOCK_EXPERIMENTS.filter(e => e.status === 'completed');
  const chartData = completedExps.map(e => ({
    date: new Date(e.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
    name: e.name,
    success_rate: e.success_rate ? e.success_rate * 100 : null,
    assertion_rate: e.total_assertions > 0 ? (e.passed_assertions / e.total_assertions) * 100 : null,
    avg_tokens: e.avg_tokens ? e.avg_tokens / 1000 : null,
  }));

  // Calculate stats
  const avgSuccess = completedExps.length > 0
    ? completedExps.reduce((sum, e) => sum + (e.success_rate || 0), 0) / completedExps.length * 100
    : 0;
  const totalTokensK = completedExps.reduce((sum, e) => sum + (e.avg_tokens || 0), 0) / 1000;
  const trend = completedExps.length >= 2 && completedExps[completedExps.length - 1].success_rate! > completedExps[0].success_rate! ? 'up' : 'flat';

  const toggleMetric = (key: 'success' | 'assertion' | 'tokens') => {
    const active = Object.values(enabledMetrics).filter(Boolean).length;
    if (enabledMetrics[key] && active <= 1) return; // Prevent disabling all
    setEnabledMetrics(prev => ({ ...prev, [key]: !prev[key] }));
  };

  return (
    <Layout>
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold">Evaluation</h1>
            <p className="text-gray-500">Run and manage evaluation experiments</p>
          </div>
          <div className="flex gap-2">
            <Link to="/evaluation/compare"><Button variant="secondary">Compare Experiments</Button></Link>
            <Link to="/evaluation/new">
              <Button className="gap-1"><Plus className="h-4 w-4" />New Experiment</Button>
            </Link>
          </div>
        </div>

        {/* Learning Trends - Collapsible */}
        <Card className="overflow-hidden">
          <div
            className="p-6 cursor-pointer hover:bg-gray-50 transition-colors"
            onClick={() => setTrendsExpanded(!trendsExpanded)}
          >
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <TrendingUp className="h-5 w-5 text-blue-500" />
                <span className="font-semibold">Learning Trends</span>
                <div className="flex items-center gap-4 text-sm text-gray-500">
                  <span>{completedExps.length} experiments</span>
                  <span className={cn('font-medium', avgSuccess >= 70 ? 'text-green-600' : avgSuccess >= 50 ? 'text-amber-600' : 'text-red-600')}>
                    {avgSuccess.toFixed(1)}%
                  </span>
                  <span>avg task success</span>
                  {trend === 'up' && <span className="text-xs text-green-500">(improving)</span>}
                </div>
              </div>
              <Button variant="ghost" size="sm" className="p-1">
                {trendsExpanded ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
              </Button>
            </div>
          </div>

          {trendsExpanded && (
            <CardContent className="border-t pt-4">
              {/* Controls */}
              <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                  <label className="text-sm text-gray-500">Time:</label>
                  <Select
                    value={timeWindow}
                    onChange={(e) => setTimeWindow(e.target.value)}
                    options={[
                      { value: 'all', label: 'All time' },
                      { value: '7d', label: 'Last 7 days' },
                      { value: '30d', label: 'Last 30 days' },
                    ]}
                    className="w-32"
                  />
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-sm text-gray-500">Show:</span>
                  <button
                    onClick={() => toggleMetric('success')}
                    className={cn(
                      'px-2 py-1 text-xs rounded-full border transition-colors',
                      enabledMetrics.success ? 'border-transparent text-white bg-green-500' : 'border-gray-300 text-gray-500'
                    )}
                  >Task Success %</button>
                  <button
                    onClick={() => toggleMetric('assertion')}
                    className={cn(
                      'px-2 py-1 text-xs rounded-full border transition-colors',
                      enabledMetrics.assertion ? 'border-transparent text-white bg-blue-500' : 'border-gray-300 text-gray-500'
                    )}
                  >Assertion Pass %</button>
                  <button
                    onClick={() => toggleMetric('tokens')}
                    className={cn(
                      'px-2 py-1 text-xs rounded-full border transition-colors',
                      enabledMetrics.tokens ? 'border-transparent text-white bg-amber-500' : 'border-gray-300 text-gray-500'
                    )}
                  >Avg Tokens (K)</button>
                </div>
              </div>

              {/* Chart */}
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={chartData} margin={{ top: 5, right: 30, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-gray-200" />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                    <YAxis yAxisId="left" domain={[0, 100]} tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}%`} />
                    {enabledMetrics.tokens && (
                      <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}K`} />
                    )}
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0]?.payload;
                        return (
                          <div className="rounded-lg border bg-white p-3 shadow-lg text-sm">
                            <p className="font-medium mb-1">{d.name}</p>
                            <p className="text-xs text-gray-500 mb-2">{d.date}</p>
                            {d.success_rate != null && enabledMetrics.success && (
                              <p className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-green-500" />Task Success: {d.success_rate.toFixed(1)}%</p>
                            )}
                            {d.assertion_rate != null && enabledMetrics.assertion && (
                              <p className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-blue-500" />Assertions: {d.assertion_rate.toFixed(1)}%</p>
                            )}
                            {d.avg_tokens != null && enabledMetrics.tokens && (
                              <p className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-amber-500" />Tokens: {d.avg_tokens.toFixed(1)}K</p>
                            )}
                          </div>
                        );
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    {enabledMetrics.success && (
                      <Line yAxisId="left" type="monotone" dataKey="success_rate" name="Task Success %" stroke="#22c55e" strokeWidth={2} dot={{ fill: '#22c55e', r: 4 }} connectNulls />
                    )}
                    {enabledMetrics.assertion && (
                      <Line yAxisId="left" type="monotone" dataKey="assertion_rate" name="Assertion Pass %" stroke="#3b82f6" strokeWidth={2} dot={{ fill: '#3b82f6', r: 4 }} connectNulls />
                    )}
                    {enabledMetrics.tokens && (
                      <Area yAxisId="right" type="monotone" dataKey="avg_tokens" name="Avg Tokens (K)" stroke="#f59e0b" fill="#f59e0b" fillOpacity={0.1} strokeWidth={2} connectNulls />
                    )}
                  </ComposedChart>
                </ResponsiveContainer>
              </div>

              {/* Summary stats footer */}
              <div className="flex items-center justify-around mt-4 pt-4 border-t text-sm">
                <div className="text-center">
                  <p className="text-gray-500">Experiments</p>
                  <p className="font-semibold text-lg">{completedExps.length}</p>
                </div>
                <div className="text-center">
                  <p className="text-gray-500">Avg Task Success</p>
                  <p className={cn('font-semibold text-lg', avgSuccess >= 70 ? 'text-green-600' : avgSuccess >= 50 ? 'text-amber-600' : 'text-red-600')}>
                    {avgSuccess.toFixed(1)}%
                  </p>
                </div>
                <div className="text-center">
                  <p className="text-gray-500">Total Tokens</p>
                  <p className="font-semibold text-lg">{totalTokensK.toFixed(0)}K</p>
                </div>
                <div className="text-center">
                  <p className="text-gray-500">Trend</p>
                  <p className={cn('font-semibold text-lg', trend === 'up' ? 'text-green-600' : 'text-gray-500')}>
                    {trend === 'up' ? 'Improving' : 'Stable'}
                  </p>
                </div>
              </div>
            </CardContent>
          )}
        </Card>

        {/* Experiments Table */}
        <Card>
          <div className="p-4 border-b flex items-center gap-4">
            <Select
              options={[
                { value: '', label: 'All statuses' },
                { value: 'pending', label: 'Pending' },
                { value: 'running', label: 'Running' },
                { value: 'completed', label: 'Completed' },
              ]}
              className="w-36"
            />
            <span className="text-sm text-gray-500 ml-auto">{MOCK_EXPERIMENTS.length} experiments</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="border-b bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Name</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Type</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Dataset</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Progress</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Success %</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Created</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {MOCK_EXPERIMENTS.map(exp => (
                  <tr key={exp.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <Link to={`/evaluation/${exp.id}`} className="font-medium text-blue-600 hover:underline">
                        {exp.name}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{exp.experiment_type}</td>
                    <td className="px-4 py-3 text-sm text-gray-600">{exp.dataset_split}</td>
                    <td className="px-4 py-3">
                      <Badge variant={exp.status === 'completed' ? 'success' : exp.status === 'running' ? 'info' : 'default'}>
                        {exp.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-3 text-sm">{exp.tasks_completed}/{exp.tasks_total}</td>
                    <td className="px-4 py-3 text-sm">
                      {exp.success_rate ? `${(exp.success_rate * 100).toFixed(1)}%` : '-'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{formatDate(exp.created_at).split(',')[0]}</td>
                    <td className="px-4 py-3">
                      <div className="flex gap-1">
                        {exp.status === 'pending' && (
                          <Button variant="ghost" size="sm" className="gap-1">
                            <PlayCircle className="h-3 w-3" />Start
                          </Button>
                        )}
                        {exp.status === 'running' && (
                          <Button variant="ghost" size="sm" className="gap-1">
                            <StopCircle className="h-3 w-3" />Stop
                          </Button>
                        )}
                        {exp.status !== 'running' && (
                          <Button variant="ghost" size="sm" className="text-red-600">
                            <Trash2 className="h-3 w-3" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </Layout>
  );
}

function EvaluationDetailPage() {
  const { experimentId } = useParams();
  const exp = MOCK_EXPERIMENTS.find(e => e.id === experimentId) || MOCK_EXPERIMENTS[0];
  const progress = exp.tasks_total > 0 ? (exp.tasks_completed / exp.tasks_total) * 100 : 0;

  return (
    <Layout>
      <div className="space-y-6">
        <Link to="/evaluation">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeft className="h-4 w-4" />Back to Experiments
          </Button>
        </Link>

        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <h1 className="text-2xl font-bold">{exp.name}</h1>
              <Badge variant={exp.status === 'completed' ? 'success' : exp.status === 'running' ? 'info' : 'default'}>
                {exp.status}
              </Badge>
            </div>
            <p className="mt-1 text-gray-500">{exp.experiment_type} &bull; {exp.dataset_split}</p>
          </div>
          <div className="flex gap-2">
            {exp.status === 'pending' && <Button>Start Experiment</Button>}
            {exp.status === 'running' && <Button variant="secondary">Stop</Button>}
            {exp.status !== 'running' && <Button variant="destructive">Delete</Button>}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            {/* Progress */}
            <Card>
              <CardHeader><CardTitle>Progress</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between text-sm">
                  <span>Tasks Completed</span>
                  <span>{exp.tasks_completed} / {exp.tasks_total}</span>
                </div>
                <ProgressBar
                  value={progress}
                  variant={exp.status === 'completed' ? 'success' : exp.status === 'failed' ? 'error' : 'default'}
                />
                {exp.status === 'running' && (
                  <p className="text-sm text-gray-500">Experiment is running...</p>
                )}
              </CardContent>
            </Card>

            {/* Task Results */}
            <Card>
              <CardHeader><CardTitle>Task Results</CardTitle></CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead className="border-b">
                      <tr>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Task ID</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Session</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Result</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Iterations</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Duration</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Tests</th>
                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500">Outcomes</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {MOCK_TASK_RESULTS.map(result => (
                        <tr key={result.id} className="hover:bg-gray-50">
                          <td className="px-3 py-2 font-mono text-xs">{result.task_id}</td>
                          <td className="px-3 py-2 font-mono text-xs">
                            {result.session_id ? (
                              <Link to={`/sessions/${result.session_id}`} className="text-blue-600 hover:underline">
                                {result.session_id.slice(0, 8)}
                              </Link>
                            ) : '-'}
                          </td>
                          <td className="px-3 py-2">
                            <Badge variant={result.success ? 'success' : 'error'}>
                              {result.success ? 'Success' : 'Failed'}
                            </Badge>
                          </td>
                          <td className="px-3 py-2 text-sm">{result.iterations}</td>
                          <td className="px-3 py-2 text-sm">{(result.duration_ms / 1000).toFixed(1)}s</td>
                          <td className="px-3 py-2 text-sm">
                            <span className={result.test_results.failures.length > 0 ? 'text-red-600' : 'text-green-600'}>
                              {result.test_results.passes.length}/{result.test_results.num_tests}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            <div className="flex flex-wrap gap-1">
                              {result.micro_outcomes.solved > 0 && <Badge variant="success" className="text-[10px] px-1">{result.micro_outcomes.solved}s</Badge>}
                              {result.micro_outcomes.progress > 0 && <Badge variant="info" className="text-[10px] px-1">{result.micro_outcomes.progress}p</Badge>}
                              {result.micro_outcomes.stuck > 0 && <Badge variant="warning" className="text-[10px] px-1">{result.micro_outcomes.stuck}st</Badge>}
                              {result.micro_outcomes.error > 0 && <Badge variant="error" className="text-[10px] px-1">{result.micro_outcomes.error}e</Badge>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Sidebar */}
          <div className="space-y-6">
            <Card>
              <CardHeader><CardTitle>Statistics</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="text-center">
                  <span className={cn(
                    'text-4xl font-bold',
                    exp.success_rate && exp.success_rate >= 0.7 ? 'text-green-600' :
                    exp.success_rate && exp.success_rate >= 0.5 ? 'text-yellow-600' : 'text-red-600'
                  )}>
                    {exp.success_rate ? `${(exp.success_rate * 100).toFixed(1)}%` : '-'}
                  </span>
                  <p className="text-sm text-gray-500">Task Success %</p>
                </div>
                <div className="text-center border-t pt-4">
                  <span className="text-3xl font-bold text-blue-600">
                    {exp.total_assertions > 0 ? `${((exp.passed_assertions / exp.total_assertions) * 100).toFixed(1)}%` : '-'}
                  </span>
                  <p className="text-sm text-gray-500">Assertion Pass %</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {exp.passed_assertions} / {exp.total_assertions} assertions
                  </p>
                </div>
                <div className="grid grid-cols-2 gap-4 text-center border-t pt-4">
                  <div>
                    <span className="block font-semibold text-green-600">
                      {MOCK_TASK_RESULTS.filter(r => r.success).length}
                    </span>
                    <span className="text-sm text-gray-500">Succeeded</span>
                  </div>
                  <div>
                    <span className="block font-semibold text-red-600">
                      {MOCK_TASK_RESULTS.filter(r => !r.success).length}
                    </span>
                    <span className="text-sm text-gray-500">Failed</span>
                  </div>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Configuration</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Dataset</span>
                  <span>{exp.dataset_split}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Type</span>
                  <span>{exp.experiment_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Task Limit</span>
                  <span>{exp.config.task_limit || 'All'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Turns/Task</span>
                  <span>{exp.config.turns_per_task}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Checkpoint</span>
                  <span>{exp.config.checkpoint_interval}</span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader><CardTitle>Metadata</CardTitle></CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-500">Created</span>
                  <span>{formatDate(exp.created_at).split(',')[0]}</span>
                </div>
                {exp.started_at && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Started</span>
                    <span>{formatDate(exp.started_at).split(',')[0]}</span>
                  </div>
                )}
                {exp.completed_at && (
                  <div className="flex justify-between">
                    <span className="text-gray-500">Completed</span>
                    <span>{formatDate(exp.completed_at).split(',')[0]}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-gray-500">ID</span>
                  <span className="font-mono text-xs">{exp.id.slice(0, 8)}...</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </Layout>
  );
}

function NewExperimentPage() {
  const [name, setName] = useState('');
  const [type, setType] = useState('baseline');
  const [dataset, setDataset] = useState('test_normal');
  const [taskLimit, setTaskLimit] = useState('');
  const [turnsPerTask, setTurnsPerTask] = useState(20);
  const [checkpointInterval, setCheckpointInterval] = useState(10);

  return (
    <Layout>
      <div className="mx-auto max-w-2xl space-y-6">
        <Link to="/evaluation">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeft className="h-4 w-4" />Back to Experiments
          </Button>
        </Link>

        <Card>
          <form onSubmit={(e) => e.preventDefault()}>
            <CardHeader><CardTitle>Create Experiment</CardTitle></CardHeader>
            <CardContent className="space-y-6">
              <div>
                <label className="mb-1 block text-sm font-medium">Name</label>
                <Input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g., Baseline Evaluation 2025-01"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium">Dataset Split</label>
                  <Select
                    value={dataset}
                    onChange={(e) => setDataset(e.target.value)}
                    options={[
                      { value: 'test_normal', label: 'Test Normal' },
                      { value: 'test_challenge', label: 'Test Challenge' },
                      { value: 'train', label: 'Train' },
                      { value: 'dev', label: 'Dev' },
                    ]}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Experiment Type</label>
                  <Select
                    value={type}
                    onChange={(e) => setType(e.target.value)}
                    options={[
                      { value: 'baseline', label: 'Baseline' },
                      { value: 'learning_curve', label: 'Learning Curve' },
                      { value: 'bullet_evolution', label: 'Bullet Evolution' },
                    ]}
                  />
                </div>
              </div>

              <div className="space-y-4 rounded-lg border p-4">
                <div className="text-sm font-medium text-gray-700">Advanced Options</div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Task Limit</label>
                  <Input
                    type="number"
                    value={taskLimit}
                    onChange={(e) => setTaskLimit(e.target.value)}
                    placeholder="Leave empty for all tasks"
                  />
                  <p className="mt-1 text-xs text-gray-500">Maximum number of tasks (empty = all)</p>
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Turns Per Task ({turnsPerTask})</label>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    value={turnsPerTask}
                    onChange={(e) => setTurnsPerTask(parseInt(e.target.value))}
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium">Checkpoint Interval ({checkpointInterval})</label>
                  <input
                    type="range"
                    min="5"
                    max="50"
                    step="5"
                    value={checkpointInterval}
                    onChange={(e) => setCheckpointInterval(parseInt(e.target.value))}
                    className="w-full"
                  />
                  <p className="mt-1 text-xs text-gray-500">Tasks between progress checkpoints</p>
                </div>
              </div>
            </CardContent>
            <div className="flex gap-2 px-5 pb-5">
              <Link to="/evaluation" className="flex-1">
                <Button variant="secondary" className="w-full">Cancel</Button>
              </Link>
              <Button type="submit" className="flex-1" disabled={!name.trim()}>
                Create Experiment
              </Button>
            </div>
          </form>
        </Card>
      </div>
    </Layout>
  );
}

function ComparePage() {
  const completedExps = MOCK_EXPERIMENTS.filter(e => e.status === 'completed');

  return (
    <Layout>
      <div className="space-y-6">
        <Link to="/evaluation">
          <Button variant="ghost" size="sm" className="gap-1">
            <ChevronLeft className="h-4 w-4" />Back to Evaluation
          </Button>
        </Link>

        <div>
          <h1 className="text-2xl font-bold">Compare Experiments</h1>
          <p className="text-gray-500">Side-by-side comparison of evaluation results</p>
        </div>

        <Card>
          <CardContent className="p-4">
            <div className="flex gap-4 items-center">
              <Select
                className="flex-1"
                options={[
                  { value: '', label: 'Select first experiment...' },
                  ...completedExps.map(e => ({ value: e.id, label: e.name }))
                ]}
              />
              <span className="text-gray-400 font-medium">vs</span>
              <Select
                className="flex-1"
                options={[
                  { value: '', label: 'Select second experiment...' },
                  ...completedExps.map(e => ({ value: e.id, label: e.name }))
                ]}
              />
              <Button>Compare</Button>
            </div>
          </CardContent>
        </Card>

        <div className="grid grid-cols-2 gap-6">
          <Card>
            <CardHeader><CardTitle>{completedExps[0]?.name}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-500">Success Rate</span>
                <span className="font-medium">{((completedExps[0]?.success_rate || 0) * 100).toFixed(1)}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Assertion Pass</span>
                <span className="font-medium">
                  {completedExps[0] ? ((completedExps[0].passed_assertions / completedExps[0].total_assertions) * 100).toFixed(1) : 0}%
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Tasks</span>
                <span className="font-medium">{completedExps[0]?.tasks_total}</span>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>{completedExps[2]?.name}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between">
                <span className="text-gray-500">Success Rate</span>
                <span className="font-medium text-green-600">
                  {((completedExps[2]?.success_rate || 0) * 100).toFixed(1)}% (+13%)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Assertion Pass</span>
                <span className="font-medium text-green-600">
                  {completedExps[2] ? ((completedExps[2].passed_assertions / completedExps[2].total_assertions) * 100).toFixed(1) : 0}% (+13%)
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-500">Tasks</span>
                <span className="font-medium">{completedExps[2]?.tasks_total}</span>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </Layout>
  );
}

// ============================================================================
// APP
// ============================================================================

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<ChatPage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/library/:bulletId" element={<BulletDetailPage />} />
        <Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />
        <Route path="/learning-loop" element={<LearningLoopPage />} />
        <Route path="/system" element={<SystemPage />} />
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/evaluation/new" element={<NewExperimentPage />} />
        <Route path="/evaluation/compare" element={<ComparePage />} />
        <Route path="/evaluation/:experimentId" element={<EvaluationDetailPage />} />
      </Routes>
    </HashRouter>
  );
}
