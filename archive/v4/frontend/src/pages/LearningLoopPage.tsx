/**
 * Learning Loop documentation page - v3 Architecture
 * Features: Overview diagram, collapsible service details with Mermaid sequence diagrams
 */

import { AppLayout } from '@/components/layouts/AppLayout';
import { PageContainer } from '@/components/layouts/MainContent';
import { Card, CardContent } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { Mermaid } from '@/components/ui/Mermaid';
import { Collapsible, ServiceHeader } from '@/components/ui/Collapsible';

// ============================================================================
// MERMAID DIAGRAM DEFINITIONS
// ============================================================================

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
    Note right of S: {session_id, turn_number,<br/>domain, problem_context,<br/>cluster_id?}
    K->>A: consume event

    alt Turn 1 (no cluster_id)
        A->>A: extract task from user input
        A->>A: LLM: normalize to "When [X]..."
        A->>DB: embed situation
        A->>DB: find nearest cluster<br/>(centroid similarity > 0.65)
    else Turn 2+ (has cluster_id)
        A->>R: get cached embedding
    end

    rect rgb(240, 249, 255)
        Note over A,DB: Two-Path Retrieval
        A->>DB: Path 1: Vector search<br/>(situation_embedding, threshold=0.50)
        A->>DB: Path 2: Cluster solutions<br/>(solved_by edges)
        A->>A: merge unique bullets
    end

    alt No candidates found
        A->>DB: cold start: random untested bullets
    end

    rect rgb(254, 243, 199)
        Note over A,DB: Filtering & Scoring
        A->>DB: get caused_failure edges<br/>for this cluster
        A->>A: exclude harmful bullets
        loop For each candidate
            A->>A: alpha = helpful + 1
            A->>A: beta = harmful + 0.2*neutral + 1
            A->>A: ts_sample = Beta(alpha, beta)
            A->>A: age_decay = 0.995^days
            A->>A: score = similarity * ts * decay
        end
        A->>A: filter TS floor (< 0.25)
        A->>A: sort by score, take top 8
    end

    A->>R: write session:{id}:turn:{n}:bullets
    A->>R: write bullets_cache (fallback)
    A->>R: write bullets_ready signal
`;

const REFLECTOR_DIAGRAM = `
sequenceDiagram
    autonumber
    participant S as Session
    participant K as Kafka
    participant R as REFLECTOR
    participant LLM as Claude API
    participant DB as PostgreSQL

    Note over S,R: Turn Buffering (per turn)
    S->>K: llm.response.received
    Note right of S: {turn_number, user_message,<br/>assistant_response, bullets_shown}
    K->>R: consume
    R->>R: buffer in memory<br/>(max 100 turns, TTL 1h)

    Note over S,R: Session Analysis (on end)
    S->>K: session.ended
    Note right of S: {session_id, success}
    K->>R: trigger analysis
    R->>R: pop buffered turns
    R->>DB: fetch bullet content

    rect rgb(243, 232, 255)
        Note over R,LLM: LLM Turn Analysis
        R->>LLM: analyze turns prompt
        Note right of R: bullets_json, turns_json,<br/>session_success flag
        LLM-->>R: micro_outcome per turn<br/>+ bullets_helped/harmed
    end

    rect rgb(254, 226, 226)
        Note over R,DB: Attribution & Counter Updates
        loop For each turn
            loop For each bullet shown
                alt Bullet helped
                    R->>DB: helpful_count++<br/>last_validated_at = NOW()
                else Bullet harmed
                    R->>DB: harmful_count++
                    R->>DB: CREATE/UPDATE caused_failure edge
                    Note right of DB: weight = 1 - 1/(evidence+2)
                else Neutral
                    R->>DB: neutral_count++
                end
            end
        end
    end

    rect rgb(220, 252, 231)
        Note over R,K: AKU Extraction (stuck→recovery)
        R->>R: find stuck/error → progress/solved
        loop For each recovery
            R->>LLM: extract AKU from turn pair
            R->>R: validate (situation≥10, assertion≥20)
            R->>K: aku.proposed
            Note right of K: source: "reflector"
        end
    end

    R->>K: attribution.resolved
    Note right of K: resolved_turns[], helped[],<br/>harmed[], similarity score
`;

const CURATOR_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant C as CURATOR
    participant E as Embedding API
    participant DB as PostgreSQL

    K->>C: aku.proposed
    Note right of K: {situation, assertion,<br/>modality, polarity, source}

    rect rgb(254, 243, 199)
        Note over C: Quality Gate
        C->>C: validate assertion ≥ 20 chars
        C->>C: validate situation ≥ 10 chars
        C->>C: validate modality ∈ {must, should, could}
        C->>C: validate polarity ∈ {do, dont, know}
        C->>C: check low-quality patterns
        Note right of C: UUID-like, generic "when using", etc.
        alt Invalid
            C->>C: reject, log reason
            Note over C: No event emitted
        end
    end

    rect rgb(219, 234, 254)
        Note over C,E: Embedding Generation
        C->>E: embed(situation)
        E-->>C: situation_embedding
        C->>E: embed(assertion)
        E-->>C: assertion_embedding
    end

    rect rgb(243, 232, 255)
        Note over C,DB: Deduplication Check
        C->>DB: SELECT bullet WHERE<br/>1 - (assertion_embedding <=> query) > threshold
        Note right of DB: threshold: reflector=0.70<br/>strategist=0.90

        alt Duplicate found
            C->>DB: UPDATE evidence_count++
            C->>K: bullet.merged
            Note right of K: {existing_bullet_id}
        else New bullet
            C->>C: derive category from polarity
            Note right of C: dont→constraints<br/>know→cheat_sheets<br/>do→solutions
            C->>DB: INSERT playbook_bullets
            Note right of DB: status='candidate'<br/>counters=0, evidence=1
            C->>K: bullet.accepted
            Note right of K: {bullet_id, category}
        end
    end
`;

const CLUSTERER_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant Cl as CLUSTERER
    participant E as Embedding API
    participant DB as PostgreSQL

    rect rgb(219, 234, 254)
        Note over K,Cl: Handle attribution.resolved
        K->>Cl: attribution.resolved
        Note right of K: {resolved_situation, resolved_turns[],<br/>helped[], harmed[], similarity}

        Cl->>E: embed(resolved_situation)
        E-->>Cl: situation_embedding
        Cl->>DB: find nearest cluster<br/>(centroid similarity > 0.65)

        alt Cluster not found
            Cl->>DB: CREATE new cluster
            Note right of DB: label from situation
        end

        loop For each turn
            Cl->>DB: UPDATE session_turns<br/>SET sub_task, micro_outcome,<br/>bullets_helped[], bullets_harmed[]
            alt micro_outcome = stuck/error
                Cl->>DB: cluster.failure_count++
            else micro_outcome = solved
                Cl->>DB: cluster.success_count++
            end
        end

        loop For each helped bullet
            Cl->>DB: UPSERT solved_by edge
            Note right of DB: weight=1.0, evidence++
        end
    end

    rect rgb(254, 243, 199)
        Note over Cl,DB: Status Transitions
        Cl->>DB: candidate → active<br/>WHERE helpful_count ≥ 3
        Cl->>DB: active → archived<br/>WHERE harmful > 2*helpful<br/>AND age > 7 days
    end

    rect rgb(220, 252, 231)
        Note over K,Cl: Handle bullet.accepted
        K->>Cl: bullet.accepted
        Note right of K: {bullet_id, situation}
        Cl->>DB: fetch situation_embedding
        Cl->>DB: find/create cluster
        Cl->>DB: CREATE solved_by edge
        Note right of DB: initial weight=1.0
    end

    rect rgb(243, 232, 255)
        Note over K,Cl: Handle bullet.merged
        K->>Cl: bullet.merged
        Cl->>Cl: log only (existing links preserved)
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
    alt Cooldown not passed
        L->>L: skip analysis
    end

    rect rgb(254, 226, 226)
        Note over L,DB: Gap Detection
        L->>DB: SELECT clusters WHERE<br/>failure_count ≥ 3<br/>AND solved_by edges = 0
        loop For each gap
            L->>DB: fetch 3 sample failed turns
            L->>K: library.gap.detected
            Note right of K: {cluster_id, cluster_label,<br/>failure_count, sample_turns[]}
        end
    end

    rect rgb(254, 243, 199)
        Note over L,DB: Struggling Cluster Detection
        L->>DB: SELECT clusters WHERE<br/>has solved_by edges<br/>AND success_rate < 50%<br/>AND turn_count ≥ 5
        loop For each struggling cluster
            L->>DB: fetch existing solutions (up to 5)
            L->>DB: fetch 3 sample failed turns
            L->>K: library.cluster.struggling
            Note right of K: {cluster_id, success_rate,<br/>existing_solutions[], sample_failures[]}
        end
    end

    rect rgb(219, 234, 254)
        Note over L,DB: Auto-Archive Harmful
        L->>DB: UPDATE playbook_bullets<br/>SET status = 'archived'<br/>WHERE harmful_count ≥ 5<br/>AND harmful > helpful
        Note right of DB: No event emitted<br/>Direct database update
    end
`;

const STRATEGIST_DIAGRAM = `
sequenceDiagram
    autonumber
    participant K as Kafka
    participant St as STRATEGIST
    participant LLM as Claude API
    participant E as Embedding API
    participant DB as PostgreSQL

    alt Gap Event
        K->>St: library.gap.detected
        Note right of K: {cluster_id, cluster_label,<br/>failure_count, sample_turns[]}
    else Struggling Event
        K->>St: library.cluster.struggling
        Note right of K: {cluster_id, success_rate,<br/>existing_solutions[], sample_failures[]}
    end

    rect rgb(243, 232, 255)
        Note over St: In-Memory Dedup
        St->>St: check cluster_id in processed set
        alt Already processed
            St->>St: skip (prevent re-synthesis)
        else New cluster
            St->>St: add to processed set<br/>(max 100, keeps last 50)
        end
    end

    rect rgb(219, 234, 254)
        Note over St,LLM: LLM Synthesis
        St->>St: format sample turns
        alt Gap event
            St->>LLM: SYNTHESIS_GAP_USER prompt
            Note right of LLM: cluster_label, failure_count,<br/>formatted sample_turns
        else Struggling event
            St->>LLM: SYNTHESIS_STRUGGLING_USER prompt
            Note right of LLM: cluster_label, success_rate,<br/>existing_solutions, sample_failures
        end
        LLM-->>St: synthesized AKU
        Note right of St: situation, assertion,<br/>modality, polarity
    end

    St->>St: validate AKU
    Note right of St: situation≥10, assertion≥20,<br/>valid modality/polarity

    rect rgb(254, 243, 199)
        Note over St,DB: Pre-Synthesis Dedup
        St->>E: embed(assertion)
        E-->>St: assertion_embedding
        St->>DB: SELECT WHERE<br/>1 - (assertion_embedding <=> query) > 0.90<br/>AND status IN ('candidate', 'active')
        alt Duplicate exists
            St->>St: skip emission
            Note over St: Saves LLM tokens
        else No duplicate
            St->>K: aku.proposed
            Note right of K: source: "strategist"<br/>session_id: "synthetic-{cluster_id}"
        end
    end

    Note over K: aku.proposed → CURATOR flow
`;

// ============================================================================
// COMPONENT
// ============================================================================

function LearningLoopPage() {
  return (
    <AppLayout>
      <PageContainer>
        <div className="space-y-10 pb-12">
          {/* Header */}
          <div className="border-b border-gray-200 pb-6 dark:border-gray-700">
            <h1 className="text-3xl font-bold tracking-tight">Learning Loop</h1>
            <p className="mt-3 text-lg text-gray-600 dark:text-gray-300">
              Event-driven learning system that observes sessions, extracts patterns, and improves
              responses through Thompson Sampling.
            </p>
          </div>

          {/* Architecture Overview */}
          <section>
            <h2 className="mb-4 text-xl font-semibold">System Overview</h2>
            <p className="mb-6 text-gray-600 dark:text-gray-400">
              The complete flow from session request to learning feedback. Sessions emit events,
              the Learning Loop processes them asynchronously, and Strategic Agents fill knowledge gaps.
            </p>
            <Card>
              <CardContent className="pt-6">
                <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                  <Mermaid chart={OVERVIEW_DIAGRAM} />
                </div>
              </CardContent>
            </Card>
          </section>

          {/* Learning Loop Services - Collapsible */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Learning Loop Services</h2>
            <div className="space-y-4">
              {/* ADVISOR */}
              <Collapsible
                colorTheme="amber"
                header={
                  <ServiceHeader
                    icon="A"
                    name="ADVISOR"
                    role="Selection"
                    brief="Selects bullets for each turn using Thompson Sampling with cluster-aware filtering"
                    colorTheme="amber"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      ADVISOR is triggered on each turn to select the most relevant bullets. It combines
                      vector search with graph-based retrieval, then applies Thompson Sampling to balance
                      exploration (trying newer bullets) with exploitation (using proven ones).
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Two-path retrieval:</strong> Vector search (threshold=0.50) + cluster solutions via <code className="text-xs">solved_by</code> edges</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Cluster-specific filtering:</strong> Excludes bullets via <code className="text-xs">caused_failure</code> edges for the current cluster</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Thompson Sampling:</strong> <code className="text-xs">score = similarity × Beta(helpful+1, harmful+0.2*neutral+1) × age_decay</code></span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Global TS floor:</strong> Bullets below 25% TS score are excluded everywhere</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Cold start fallback:</strong> If no candidates, fetches random untested bullets</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: bullets.requested
                      </Badge>
                      <Badge className="bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                        Output: Redis (bullets + cluster_id)
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={ADVISOR_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>

              {/* REFLECTOR */}
              <Collapsible
                colorTheme="purple"
                header={
                  <ServiceHeader
                    icon="R"
                    name="REFLECTOR"
                    role="Feedback Owner"
                    brief="Owns the feedback loop: turn analysis, attribution, counters, and AKU extraction"
                    colorTheme="purple"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      REFLECTOR is the heart of the feedback loop. It buffers turn data during a session,
                      then on session end, uses an LLM to analyze each turn for micro-outcomes and determine
                      which bullets helped or harmed. It directly updates effectiveness counters and creates
                      <code className="mx-1 text-xs">caused_failure</code> edges.
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>In-memory buffering:</strong> Stores turn data (max 100 turns, TTL 1h) until session ends</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>LLM turn analysis:</strong> Classifies each turn as solved/progress/stuck/error with implicit bullet attribution</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>Direct counter updates:</strong> Updates <code className="text-xs">helpful_count</code>, <code className="text-xs">harmful_count</code>, <code className="text-xs">neutral_count</code> in PostgreSQL</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>Edge creation:</strong> Creates <code className="text-xs">caused_failure</code> edges with weight formula: <code className="text-xs">1 - 1/(evidence+2)</code></span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>AKU extraction:</strong> Detects stuck→recovery patterns and extracts learnings via LLM</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: llm.response.received
                      </Badge>
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: session.ended
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: aku.proposed
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: attribution.resolved
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={REFLECTOR_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>

              {/* CURATOR */}
              <Collapsible
                colorTheme="green"
                header={
                  <ServiceHeader
                    icon="C"
                    name="CURATOR"
                    role="Quality Gate"
                    brief="Single quality gate for all AKU sources with embedding-based deduplication"
                    colorTheme="green"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      CURATOR is the single entry point for all new bullets, whether from REFLECTOR (organic learning)
                      or STRATEGIST (synthesized). It validates AKUs, generates embeddings, checks for duplicates
                      using assertion similarity, and either stores new bullets or increments evidence on existing ones.
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Quality gate:</strong> Validates assertion≥20 chars, situation≥10 chars, valid modality/polarity</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Two-space embeddings:</strong> Generates both <code className="text-xs">situation_embedding</code> (retrieval) and <code className="text-xs">assertion_embedding</code> (dedup)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Dedup on assertion:</strong> Same situation with different solutions = OK. Same solution = merged.</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Source-based thresholds:</strong> reflector=0.70 (more lenient), strategist=0.90 (stricter)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Category derivation:</strong> dont→constraints, know→cheat_sheets, do→solutions</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: aku.proposed
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: bullet.accepted
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: bullet.merged
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={CURATOR_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>

              {/* CLUSTERER */}
              <Collapsible
                colorTheme="blue"
                header={
                  <ServiceHeader
                    icon="C"
                    name="CLUSTERER"
                    role="Graph Manager"
                    brief="Assigns turns to clusters and maintains the knowledge graph"
                    colorTheme="blue"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      CLUSTERER organizes problem space into clusters and maintains the knowledge graph.
                      It assigns sessions to clusters by embedding similarity, creates <code className="mx-1 text-xs">solved_by</code> edges
                      linking helpful bullets to clusters, and manages bullet status transitions.
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>Cluster assignment:</strong> Finds nearest cluster by centroid similarity (threshold=0.65) or creates new</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>solved_by edges:</strong> Links helpful bullets to clusters (weight=1.0, evidence incremented)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>Cluster stats:</strong> Updates turn_count, success_count, failure_count per cluster</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>Status transitions:</strong> candidate→active (3+ helpful), active→archived (harmful&gt;2*helpful, 7+ days)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>Semantic bridge:</strong> If initial vs resolved situation differ (&lt;0.70), links to both clusters</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: attribution.resolved
                      </Badge>
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: bullet.accepted
                      </Badge>
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: bullet.merged
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={CLUSTERER_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>
            </div>
          </section>

          {/* Strategic Agents - Collapsible */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Strategic Agents</h2>
            <div className="space-y-4">
              {/* LIBRARIAN */}
              <Collapsible
                colorTheme="slate"
                header={
                  <ServiceHeader
                    icon="L"
                    name="LIBRARIAN"
                    role="Passive / Analytical"
                    brief="Analyzes library for gaps, struggling clusters, and harmful bullets"
                    colorTheme="slate"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      LIBRARIAN is the passive intelligence layer. It periodically analyzes the knowledge library
                      to detect gaps (clusters with failures but no solutions), identify struggling clusters
                      (has solutions but poor success rate), and auto-archive harmful bullets.
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-amber-500" />
                        <span><strong>Gap detection:</strong> Clusters with failure_count≥3 and zero solved_by edges</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-yellow-500" />
                        <span><strong>Struggling clusters:</strong> Has solved_by edges but success_rate&lt;50% with turn_count≥5</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-red-500" />
                        <span><strong>Auto-archive:</strong> Bullets where harmful_count≥5 AND harmful&gt;helpful (no event, direct DB update)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-gray-500" />
                        <span><strong>Cooldown:</strong> Analysis runs max once per 60 seconds to prevent thundering herd</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Triggered by: attribution.resolved
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: library.gap.detected
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: library.cluster.struggling
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={LIBRARIAN_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>

              {/* STRATEGIST */}
              <Collapsible
                colorTheme="red"
                header={
                  <ServiceHeader
                    icon="S"
                    name="STRATEGIST"
                    role="Active / Strategic"
                    brief="Synthesizes new bullets via LLM to fill knowledge gaps"
                    colorTheme="red"
                  />
                }
              >
                <div className="space-y-6">
                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Purpose</h4>
                    <p className="text-gray-600 dark:text-gray-400">
                      STRATEGIST is the active intelligence layer. When LIBRARIAN detects gaps or struggling clusters,
                      STRATEGIST uses an LLM to synthesize new bullets based on sample failure data. It includes
                      pre-synthesis deduplication to avoid creating redundant knowledge.
                    </p>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Key Features</h4>
                    <ul className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-blue-500" />
                        <span><strong>Gap handling:</strong> Synthesizes AKU from cluster_label + sample failed turns</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-yellow-500" />
                        <span><strong>Struggling handling:</strong> Synthesizes NEW approach given existing_solutions that aren't working</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-green-500" />
                        <span><strong>Pre-synthesis dedup:</strong> Checks assertion_embedding similarity&gt;0.90 BEFORE emitting (saves tokens)</span>
                      </li>
                      <li className="flex items-start gap-2">
                        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-purple-500" />
                        <span><strong>In-memory tracking:</strong> Tracks processed cluster_ids to prevent re-synthesis (max 100)</span>
                      </li>
                    </ul>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Events</h4>
                    <div className="flex flex-wrap gap-2">
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: library.gap.detected
                      </Badge>
                      <Badge className="bg-blue-100 text-blue-700 dark:bg-blue-900 dark:text-blue-300">
                        Consumes: library.cluster.struggling
                      </Badge>
                      <Badge className="bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300">
                        Emits: aku.proposed (source: strategist)
                      </Badge>
                    </div>
                  </div>

                  <div>
                    <h4 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Sequence Diagram</h4>
                    <div className="rounded-lg border border-gray-200 bg-gray-50 p-4 dark:border-gray-700 dark:bg-gray-800">
                      <Mermaid chart={STRATEGIST_DIAGRAM} />
                    </div>
                  </div>
                </div>
              </Collapsible>
            </div>
          </section>

          {/* Thompson Sampling */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Thompson Sampling</h2>
            <Card>
              <CardContent className="pt-6">
                <div className="rounded-lg bg-gray-900 p-6 font-mono text-sm text-gray-100">
                  <div className="text-green-400">// Bullet selection formula</div>
                  <div className="mt-2">
                    <span className="text-purple-400">final_score</span> ={' '}
                    <span className="text-blue-400">similarity</span> ×{' '}
                    <span className="text-yellow-400">thompson_sample</span> ×{' '}
                    <span className="text-orange-400">age_decay</span>
                  </div>
                  <div className="mt-4 border-t border-gray-700 pt-4 text-gray-400">
                    <div>
                      alpha = helpful_count + 1
                    </div>
                    <div>
                      beta = harmful_count + 0.2 × neutral_count + 1
                    </div>
                    <div className="mt-2">
                      <span className="text-yellow-400">thompson_sample</span> = random.beta(alpha, beta)
                    </div>
                    <div>
                      <span className="text-orange-400">age_decay</span> = 0.995<sup>days</sup>{' '}
                      <span className="text-gray-500">// ~0.5% daily decay, floor 0.50</span>
                    </div>
                  </div>
                </div>
                <p className="mt-4 text-sm text-gray-600 dark:text-gray-400">
                  Thompson Sampling naturally balances exploration (trying newer bullets) with exploitation
                  (using proven ones). Bullets with more helpful outcomes score higher on average, but there's
                  always a chance for newer bullets to be selected and prove themselves.
                </p>
              </CardContent>
            </Card>
          </section>

          {/* Two-Layer Exclusion */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Two-Layer Exclusion</h2>
            <div className="grid gap-6 md:grid-cols-2">
              <div className="rounded-xl border-2 border-red-200 bg-red-50 p-6 dark:border-red-800 dark:bg-red-900/20">
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-red-500 text-xs font-bold text-white">
                    1
                  </span>
                  <span className="font-semibold text-red-700 dark:text-red-300">
                    Global: Thompson Sampling Floor
                  </span>
                </div>
                <p className="text-sm text-red-600 dark:text-red-400">
                  Bullets below 25% TS score are excluded everywhere. These are failure-mode bullets
                  with proven-poor records across all problem types.
                </p>
              </div>

              <div className="rounded-xl border-2 border-amber-200 bg-amber-50 p-6 dark:border-amber-800 dark:bg-amber-900/20">
                <div className="mb-3 flex items-center gap-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-500 text-xs font-bold text-white">
                    2
                  </span>
                  <span className="font-semibold text-amber-700 dark:text-amber-300">
                    Cluster-Specific: caused_failure Edges
                  </span>
                </div>
                <p className="text-sm text-amber-600 dark:text-amber-400">
                  Bullets excluded only for specific problem types where they caused failures.
                  A bullet may work well for some clusters but fail for others.
                </p>
              </div>
            </div>
          </section>

          {/* Micro-Outcomes */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Micro-Outcomes</h2>
            <p className="mb-4 text-gray-600 dark:text-gray-400">
              REFLECTOR classifies each turn into one of four micro-outcomes:
            </p>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <div className="rounded-xl border-2 border-green-200 bg-green-50 p-5 text-center dark:border-green-800 dark:bg-green-900/20">
                <span className="text-2xl font-bold text-green-600 dark:text-green-400">solved</span>
                <p className="mt-2 text-sm text-green-600/80 dark:text-green-400/80">
                  Task completed successfully
                </p>
              </div>
              <div className="rounded-xl border-2 border-blue-200 bg-blue-50 p-5 text-center dark:border-blue-800 dark:bg-blue-900/20">
                <span className="text-2xl font-bold text-blue-600 dark:text-blue-400">progress</span>
                <p className="mt-2 text-sm text-blue-600/80 dark:text-blue-400/80">
                  Moving forward on task
                </p>
              </div>
              <div className="rounded-xl border-2 border-amber-200 bg-amber-50 p-5 text-center dark:border-amber-800 dark:bg-amber-900/20">
                <span className="text-2xl font-bold text-amber-600 dark:text-amber-400">stuck</span>
                <p className="mt-2 text-sm text-amber-600/80 dark:text-amber-400/80">
                  Unable to make progress
                </p>
              </div>
              <div className="rounded-xl border-2 border-red-200 bg-red-50 p-5 text-center dark:border-red-800 dark:bg-red-900/20">
                <span className="text-2xl font-bold text-red-600 dark:text-red-400">error</span>
                <p className="mt-2 text-sm text-red-600/80 dark:text-red-400/80">
                  Exception or failure occurred
                </p>
              </div>
            </div>
          </section>

          {/* Event Flow Table */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Event Flow</h2>
            <Card>
              <CardContent className="overflow-x-auto pt-6">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 dark:border-gray-700">
                      <th className="pb-3 text-left font-semibold">Event</th>
                      <th className="pb-3 text-left font-semibold">Producer</th>
                      <th className="pb-3 text-left font-semibold">Consumer</th>
                      <th className="pb-3 text-left font-semibold">Purpose</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
                    <EventRow
                      event="bullets.requested"
                      producer="Session"
                      consumer="ADVISOR"
                      purpose="Trigger per-turn bullet selection"
                    />
                    <EventRow
                      event="llm.response.received"
                      producer="Session"
                      consumer="REFLECTOR"
                      purpose="Buffer turn data for analysis"
                    />
                    <EventRow
                      event="session.ended"
                      producer="Session / Eval"
                      consumer="REFLECTOR"
                      purpose="Trigger turn analysis and attribution"
                    />
                    <EventRow
                      event="aku.proposed"
                      producer="REFLECTOR / STRATEGIST"
                      consumer="CURATOR"
                      purpose="Submit new AKU for quality check"
                    />
                    <EventRow
                      event="bullet.accepted"
                      producer="CURATOR"
                      consumer="CLUSTERER"
                      purpose="New bullet stored in library"
                    />
                    <EventRow
                      event="bullet.merged"
                      producer="CURATOR"
                      consumer="CLUSTERER"
                      purpose="Evidence incremented on existing bullet"
                    />
                    <EventRow
                      event="attribution.resolved"
                      producer="REFLECTOR"
                      consumer="CLUSTERER"
                      purpose="Turn-level attribution data for clustering"
                    />
                    <EventRow
                      event="library.gap.detected"
                      producer="LIBRARIAN"
                      consumer="STRATEGIST"
                      purpose="Knowledge gap needs synthesis"
                    />
                    <EventRow
                      event="library.cluster.struggling"
                      producer="LIBRARIAN"
                      consumer="STRATEGIST"
                      purpose="Cluster needs alternative approach"
                    />
                  </tbody>
                </table>
              </CardContent>
            </Card>
          </section>

          {/* Knowledge Graph Edges */}
          <section>
            <h2 className="mb-6 text-xl font-semibold">Knowledge Graph Edges</h2>
            <p className="mb-4 text-gray-600 dark:text-gray-400">
              v3 uses only two edge types to connect clusters and bullets:
            </p>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="rounded-lg border border-gray-200 p-5 dark:border-gray-700">
                <div className="mb-2 flex items-center gap-2">
                  <span className="rounded bg-green-100 px-2 py-1 font-mono text-xs text-green-700 dark:bg-green-900 dark:text-green-300">
                    solved_by
                  </span>
                  <span className="text-sm text-gray-500">cluster → bullet</span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Links problem clusters to bullets that successfully helped solve them.
                  Created by CLUSTERER when attribution shows a bullet helped.
                </p>
              </div>
              <div className="rounded-lg border border-gray-200 p-5 dark:border-gray-700">
                <div className="mb-2 flex items-center gap-2">
                  <span className="rounded bg-red-100 px-2 py-1 font-mono text-xs text-red-700 dark:bg-red-900 dark:text-red-300">
                    caused_failure
                  </span>
                  <span className="text-sm text-gray-500">cluster → bullet</span>
                </div>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Links problem clusters to bullets that caused harm.
                  Created by REFLECTOR to enable cluster-specific exclusion.
                </p>
              </div>
            </div>
          </section>
        </div>
      </PageContainer>
    </AppLayout>
  );
}

// Helper component for event table rows
function EventRow({
  event,
  producer,
  consumer,
  purpose,
}: {
  event: string;
  producer: string;
  consumer: string;
  purpose: string;
}) {
  return (
    <tr>
      <td className="py-3">
        <code className="rounded bg-gray-100 px-2 py-0.5 text-xs dark:bg-gray-800">{event}</code>
      </td>
      <td className="py-3 text-gray-600 dark:text-gray-400">{producer}</td>
      <td className="py-3 text-gray-600 dark:text-gray-400">{consumer}</td>
      <td className="py-3 text-gray-600 dark:text-gray-400">{purpose}</td>
    </tr>
  );
}

export default LearningLoopPage;
