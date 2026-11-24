import { Navigate, Route, Routes } from 'react-router-dom'
import { ThemeProvider } from './mitra/Theme'
import { AuthProvider } from './auth/AuthProvider'
import ProtectedRoute from './auth/ProtectedRoute'
import CandidateProtectedRoute from './auth/CandidateProtectedRoute'
import LoginPage from './pages/mitra/login/LoginPage'
import JobsEmptyPage from './pages/mitra/JobsEmptyPage'
import CreateJobPage from './pages/mitra/CreateJobPage'
import JobDetailPage from './pages/mitra/JobDetailPage'
import Shell from './mitra/Shell'

import CandidatesPage from './new-pages/CandidatesPage'
import CreateCandidatePage from './new-pages/CreateCandidatePage'
import CandidateDetailPage from './new-pages/CandidateDetailPage'
import CandidateDashboardPage from './new-pages/CandidateDashboardPage'
import CandidateProfilePage from './new-pages/CandidateProfilePage'
import CandidateResumePage from './new-pages/CandidateResumePage'
import AssistantPage from './new-pages/AssistantPage'
import CandidateRegisterPage from './new-pages/CandidateRegisterPage'
import CandidateShell from './new-pages/CandidateShell'
import CandidateJobsPage from './new-pages/CandidateJobsPage'
import CandidateJobDetailPage from './new-pages/CandidateJobDetailPage'
import CandidateApplicationsPage from './new-pages/CandidateApplicationsPage'
import CandidateInterviewsPage from './new-pages/CandidateInterviewsPage'
import CandidateMessagesPage from './new-pages/CandidateMessagesPage'
import RecruiterConversationsPage from './new-pages/RecruiterConversationsPage'
import JobApplicantsPage from './new-pages/JobApplicantsPage'
import MatchesPage from './new-pages/MatchesPage'
import MessagesPage from './new-pages/MessagesPage'
import InterviewsPage from './new-pages/InterviewsPage'
import ScheduleInterviewPage from './new-pages/ScheduleInterviewPage'
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
          <Route path="/register" element={<LoginPage />} />
<Route path="/candidate/register" element={<CandidateRegisterPage />} />
<Route path="/candidate/dashboard" element={<CandidateProtectedRoute><CandidateShell><CandidateDashboardPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/profile" element={<CandidateProtectedRoute><CandidateShell><CandidateProfilePage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/resume" element={<CandidateProtectedRoute><CandidateShell><CandidateResumePage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/assistant" element={<CandidateProtectedRoute><CandidateShell><AssistantPage mode="candidate" /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/jobs" element={<CandidateProtectedRoute><CandidateShell><CandidateJobsPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/jobs/:jobId" element={<CandidateProtectedRoute><CandidateShell><CandidateJobDetailPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/applications" element={<CandidateProtectedRoute><CandidateShell><CandidateApplicationsPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/interviews" element={<CandidateProtectedRoute><CandidateShell><CandidateInterviewsPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/candidate/messages" element={<CandidateProtectedRoute><CandidateShell><CandidateMessagesPage /></CandidateShell></CandidateProtectedRoute>} />
<Route path="/conversations" element={guarded(<Shell><RecruiterConversationsPage /></Shell>)} />
<Route path="/jobs/:id/applicants" element={guarded(<Shell><JobApplicantsPage /></Shell>)} />
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
