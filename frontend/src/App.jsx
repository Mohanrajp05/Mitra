import { Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './mitra/Theme'
import { AuthProvider } from './auth/AuthProvider'
import ProtectedRoute from './auth/ProtectedRoute'
import LoginPage from './pages/mitra/LoginPage'
import JobsEmptyPage from './pages/mitra/JobsEmptyPage'
import CreateJobPage from './pages/mitra/CreateJobPage'
import JobDetailPage from './pages/mitra/JobDetailPage'
import Shell from './mitra/Shell'

import CandidatesPage from './new-pages/CandidatesPage'
import CreateCandidatePage from './new-pages/CreateCandidatePage'
import CandidateDetailPage from './new-pages/CandidateDetailPage'
import MatchesPage from './new-pages/MatchesPage'
import MessagesPage from './new-pages/MessagesPage'
import InterviewsPage from './new-pages/InterviewsPage'
import ScheduleInterviewPage from './new-pages/ScheduleInterviewPage'
import AssistantPage from './new-pages/AssistantPage'
import NewDashboardPage from './new-pages/DashboardPage'
import NewJobsPage from './new-pages/JobsPage'

function guarded(element) {
  return <ProtectedRoute>{element}</ProtectedRoute>
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<LoginPage start="signup" />} />
          <Route path="/dashboard" element={guarded(<Shell><NewDashboardPage /></Shell>)} />
          <Route path="/jobs" element={guarded(<Shell><NewJobsPage /></Shell>)} />
          <Route path="/jobs/empty" element={guarded(<JobsEmptyPage />)} />
          <Route path="/jobs/new" element={guarded(<CreateJobPage />)} />
          <Route path="/jobs/:id" element={guarded(<JobDetailPage />)} />
          <Route path="/jobs/:id/edit" element={guarded(<CreateJobPage />)} />
          <Route path="/documents" element={guarded(<Navigate to="/candidates" replace />)} />
          <Route path="/candidates" element={guarded(<Shell><CandidatesPage /></Shell>)} />
          <Route path="/candidates/new" element={guarded(<CreateCandidatePage />)} />
          <Route path="/candidates/:candidateId" element={guarded(<Shell><CandidateDetailPage /></Shell>)} />
          <Route path="/matches" element={guarded(<Shell><MatchesPage /></Shell>)} />
          <Route path="/messages" element={guarded(<Shell><MessagesPage /></Shell>)} />
          <Route path="/interviews" element={guarded(<Shell><InterviewsPage /></Shell>)} />
          <Route path="/interviews/schedule" element={guarded(<Shell><ScheduleInterviewPage /></Shell>)} />
          <Route path="/assistant" element={guarded(<Shell><AssistantPage /></Shell>)} />
          <Route path="/assistant/workspace" element={guarded(<Navigate to="/assistant" replace />)} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </ThemeProvider>
  )
}
