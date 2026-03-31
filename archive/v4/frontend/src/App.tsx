import { Routes, Route } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import HomePage from '@/pages/HomePage';
import LearningLoopPage from '@/pages/LearningLoopPage';
import KnowledgeGraphPage from '@/pages/KnowledgeGraphPage';

// Sessions
import SessionsPage from '@/pages/sessions/SessionsPage';
import SessionDetailPage from '@/pages/sessions/SessionDetailPage';

// Library
import BulletsLibraryPage from '@/pages/library/BulletsLibraryPage';
import BulletDetailPage from '@/pages/library/BulletDetailPage';

// Evaluation
import EvaluationPage from '@/pages/evaluation/EvaluationPage';
import EvaluationNewPage from '@/pages/evaluation/EvaluationNewPage';
import EvaluationDetailPage from '@/pages/evaluation/EvaluationDetailPage';
import EvaluationComparePage from '@/pages/evaluation/EvaluationComparePage';
import EpochsComparisonPage from '@/pages/evaluation/EpochsComparisonPage';

// System
import SystemPage from '@/pages/system/SystemPage';

function App() {
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/sessions" element={<SessionsPage />} />
        <Route path="/sessions/:sessionId" element={<SessionDetailPage />} />

        {/* Library */}
        <Route path="/bullets" element={<BulletsLibraryPage />} />
        <Route path="/bullets/:bulletId" element={<BulletDetailPage />} />
        <Route path="/knowledge-graph" element={<KnowledgeGraphPage />} />

        {/* Evaluation */}
        <Route path="/evaluation" element={<EvaluationPage />} />
        <Route path="/evaluation/new" element={<EvaluationNewPage />} />
        <Route path="/evaluation/compare" element={<EvaluationComparePage />} />
        <Route path="/evaluation/epochs" element={<EpochsComparisonPage />} />
        <Route path="/evaluation/:experimentId" element={<EvaluationDetailPage />} />

        {/* System */}
        <Route path="/system" element={<SystemPage />} />
        <Route path="/learning-loop" element={<LearningLoopPage />} />
      </Routes>
    </ErrorBoundary>
  );
}

export default App;
