import { Link, NavLink, useNavigate } from 'react-router-dom'
import { useState } from 'react'
import { signOut } from '../services/auth'

export default function Navbar({ session }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const email = session?.user?.email || 'Signed in'

  async function handleLogout() {
    setBusy(true)
    setError('')
    try {
      await signOut()
      navigate('/login', { replace: true })
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <header className="navbar">
      <div className="navbar-inner">
        <Link className="brand" to="/dashboard">
          <span className="brand-mark" aria-hidden="true">
            AR
          </span>
          <span>AI Recruitment Agent</span>
        </Link>

        <div className="navbar-user">
          <NavLink
            to="/ai-assistant"
            className={({ isActive }) =>
              isActive ? 'btn btn-primary btn-sm' : 'btn btn-secondary btn-sm'
            }
          >
            AI Assistant
          </NavLink>
          <span className="user-email" title={email}>
            {email}
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={handleLogout}
            disabled={busy}
          >
            {busy ? 'Signing out...' : 'Log out'}
          </button>
        </div>
      </div>
      {error && (
        <p className="navbar-error" role="alert">
          {error}
        </p>
      )}
    </header>
  )
}
