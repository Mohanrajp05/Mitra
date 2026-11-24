import { Navigate, useLocation } from 'react-router-dom'
import { useAuth } from './AuthProvider'

function RoleGate({ title, message, onRetry }) {
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

export default function ProtectedRoute({ children }) {
  const { session, loading, role, roleLoading, roleError, refreshRole } = useAuth()
  const location = useLocation()

  const waitingForRole = Boolean(session) && !role && !roleError

  if (loading || waitingForRole || (session && roleLoading)) {
    return (
      <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', background: 'var(--bg, #f6f5f8)' }}>
        <p style={{ color: 'var(--muted, #8b849c)', fontWeight: 600 }}>Checking your session…</p>
      </div>
    )
  }

  if (!session) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (roleError) {
    return (
      <RoleGate
        title="We couldn't verify your account type"
        message={roleError}
        onRetry={refreshRole}
      />
    )
  }

  // A candidate who lands on a recruiter route must be sent to their portal,
  // never shown the recruiter workspace.
  if (role === 'candidate') {
    return <Navigate to="/candidate/dashboard" replace />
  }

  if (role !== 'recruiter') {
    return (
      <RoleGate
        title="Account type unavailable"
        message="We could not determine whether this account is a recruiter or a candidate."
        onRetry={refreshRole}
      />
    )
  }

  return children
}
