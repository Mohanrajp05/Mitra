import { useEffect, useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import Icon, { Logo } from '../mitra/Icons'
import { useTheme } from '../mitra/Theme'
import { signOut, getCurrentUser } from '../services/auth'
import { useAuth } from '../auth/AuthProvider'
import Avatar from './Avatar'

const NAV = [
  { to: '/candidate/dashboard', label: 'Dashboard', icon: 'grid' },
  { to: '/candidate/jobs', label: 'Browse Jobs', icon: 'briefcase' },
  { to: '/candidate/applications', label: 'My Applications', icon: 'file' },
  { to: '/candidate/interviews', label: 'My Interviews', icon: 'calendar' },
  { to: '/candidate/messages', label: 'Messages', icon: 'mail' },
  { to: '/candidate/profile', label: 'My Profile', icon: 'users' },
  { to: '/candidate/resume', label: 'My Resume', icon: 'upload' },
  { to: '/candidate/assistant', label: 'AI Assistant', icon: 'sparkle' },
]

function CandidateNavItem({ item, collapsed }) {
  return (
    <NavLink
      to={item.to}
      className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
      title={item.label}
    >
      <Icon name={item.icon} size={18} />
      {collapsed ? null : <span className="nav-label">{item.label}</span>}
    </NavLink>
  )
}

export default function CandidateShell({ children }) {
  const navigate = useNavigate()
  const { theme, toggle } = useTheme()
  const { session } = useAuth()
  const [collapsed, setCollapsed] = useState(false)
  const [userName, setUserName] = useState('')
  const [signingOut, setSigningOut] = useState(false)

  useEffect(() => {
    let cancelled = false
    async function load() {
      const meta = session?.user?.user_metadata || {}
      const fallback = session?.user?.email ? session.user.email.split('@')[0] : ''
      if (meta.full_name || meta.name || fallback) {
        if (!cancelled) setUserName(meta.full_name || meta.name || fallback)
        return
      }
      try {
        const user = await getCurrentUser()
        if (cancelled) return
        const userMeta = user?.user_metadata || {}
        setUserName(userMeta.full_name || userMeta.name || (user?.email || '').split('@')[0] || '')
      } catch {
        if (!cancelled) setUserName('')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [session])

  async function handleSignOut() {
    if (signingOut) return
    setSigningOut(true)
    try {
      await signOut()
    } catch {
      setSigningOut(false)
    }
  }

  useEffect(() => {
    if (signingOut) navigate('/login', { replace: true })
  }, [signingOut, navigate])

  return (
    <div className={`shell ${collapsed ? 'is-collapsed' : ''}`}>
      <header className="topbar">
        <div className="topbar-brand">
          <Logo />
          <span className="role-badge role-badge-candidate">Candidate</span>
        </div>
        <span />
        <div className="top-actions">
          <button
            type="button"
            className="icon-btn"
            onClick={toggle}
            aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
          >
            <Icon name={theme === 'dark' ? 'sun' : 'moon'} size={16} />
          </button>
          <button
            type="button"
            className="icon-btn"
            onClick={handleSignOut}
            disabled={signingOut}
            aria-label="Log out"
            title="Log out"
          >
            <Icon name="logout" size={16} />
          </button>
          <span className="me">
            <Avatar name={userName || 'You'} size={34} />
            <span className="online" />
          </span>
        </div>
      </header>

      <div className="shell-body">
        <aside className="sidebar">
          <div className="nav-group">
            {!collapsed && <p className="nav-kicker">Candidate portal</p>}
            {NAV.map((item) => (
              <CandidateNavItem key={item.to} item={item} collapsed={collapsed} />
            ))}
          </div>
          <div className="side-foot">
            <button type="button" className="collapse-btn" onClick={() => setCollapsed((value) => !value)}>
              <Icon name="chevron" size={16} />
              {collapsed ? null : 'Collapse'}
            </button>
          </div>
        </aside>
        <main className="main">{children}</main>
      </div>
    </div>
  )
}
