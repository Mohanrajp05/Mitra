import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthProvider'

function CenteredMessage({ title, message, onRetry }) {
  return (
    <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg, #f6f5f8)', padding: 24 }}>
      <div style={{ maxWidth: 420, textAlign: 'center' }}>
        <h1 style={{ fontSize: 20, marginBottom: 8 }}>{title}</h1>
        <p style={{ color: 'var(--muted, #8b849c)', fontWeight: 600 }}>{message}</p>
        {onRetry && (
          <button type="button" className="btn btn-secondary" onClick={onRetry} style={{ marginTop: 12 }}>
            Try again
          </button>
        )}
      </div>
    </div>
  )
}

export default function CandidateProtectedRoute({ children }) {
  const { session, loading, role, roleLoading, roleError, refreshRole } = useAuth()
  const location = useLocation()

  const waitingForRole = Boolean(session) && !role && !roleError

  if (loading || waitingForRole || (session && roleLoading)) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg, #f6f5f8)' }}>
        <p style={{ color: 'var(--muted, #8b849c)', fontWeight: 600 }}>Checking your account…</p>
      </div>
    )
  }

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (roleError) {
    return (
      <CenteredMessage
        title="We couldn't verify your account type"
        message={roleError}
        onRetry={refreshRole}
      />
    )
  }

  if (role === 'recruiter') {
    return <Navigate to="/dashboard" replace />
  }

  if (role !== 'candidate') {
    return (
      <CenteredMessage
        title="Account type unavailable"
        message="We could not determine whether this account is a recruiter or a candidate."
        onRetry={refreshRole}
      />
    )
  }

  return children
}
