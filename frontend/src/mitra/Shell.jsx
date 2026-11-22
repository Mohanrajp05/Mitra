import { useEffect, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import Icon, { Avatar, Logo } from './Icons'
import { useTheme } from './Theme'
import { signOut } from '../services/auth'
import NotificationBell from './NotificationBell'
import { listJobs } from '../services/jobs'
import { listCandidates } from '../services/candidates'
import { listChatSessions } from '../services/chat'
import { getCurrentUser } from '../services/auth'
import { checkHealth } from '../services/health'

const NAV = {
  workspace: [
    { to: '/dashboard', label: 'Dashboard', icon: 'grid' },
    { to: '/jobs', label: 'Jobs', icon: 'briefcase', countKey: 'jobs' },
    { to: '/candidates', label: 'Candidates', icon: 'users', countKey: 'candidates' },
    { to: '/matches', label: 'Matches', icon: 'spark' },
  ],
  inbox: [
    { to: '/messages', label: 'Messages', icon: 'mail', countKey: 'sessions' },
    { to: '/interviews', label: 'Interviews', icon: 'calendar' },
  ],
  ai: [{ to: '/assistant', label: 'Assistant', icon: 'bot' }],
}

function NavItem({ item, collapsed, counts }) {
  return (
    <NavLink to={item.to} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`} title={item.label}>
      <Icon name={item.icon} size={18} />
      {collapsed ? null : <span className="nav-label">{item.label}</span>}
      {!collapsed && item.countKey && counts[item.countKey] != null ? (
        <span className="nav-count">{counts[item.countKey]}</span>
      ) : null}
    </NavLink>
  )
}

function NavGroup({ label, items, collapsed, counts }) {
  return (
    <div className="nav-group">
      {collapsed ? null : <p className="nav-kicker">{label}</p>}
      {items.map((item) => (
        <NavItem key={item.to} item={item} collapsed={collapsed} counts={counts} />
      ))}
    </div>
  )
}

export default function Shell({ children }) {
  const { theme, toggle } = useTheme()
  const navigate = useNavigate()
  const location = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [query, setQuery] = useState('')
  const [userName, setUserName] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [counts, setCounts] = useState({})
  const [backendOnline, setBackendOnline] = useState(null)
  const isAssistantPage = location.pathname === '/assistant'

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
    if (!signingOut) return
    navigate('/login', { replace: true })
  }, [signingOut, navigate])

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const user = await getCurrentUser()
        if (cancelled) return
        const meta = user?.user_metadata || {}
        const fallback = user?.email ? user?.email.split('@')[0] : ''
        setUserName(meta.full_name || meta.name || fallback)
      } catch {
        if (!cancelled) setUserName('')
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      const [jobs, candidates, sessions] = await Promise.allSettled([listJobs(), listCandidates(), listChatSessions()])
      if (cancelled) return
      setCounts((current) => ({
        ...current,
        jobs: jobs.status === 'fulfilled' && Array.isArray(jobs.value) ? jobs.value.length : current.jobs,
        candidates:
          candidates.status === 'fulfilled' && Array.isArray(candidates.value) ? candidates.value.length : current.candidates,
        sessions: sessions.status === 'fulfilled' && Array.isArray(sessions.value) ? sessions.value.length : current.sessions,
      }))
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    checkHealth()
      .then(() => {
        if (!cancelled) setBackendOnline(true)
      })
      .catch(() => {
        if (!cancelled) setBackendOnline(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <div className={`shell ${collapsed ? 'is-collapsed' : ''}`}>
      <header className={`topbar ${isAssistantPage ? 'topbar-with-back' : ''}`}>
        <div className="topbar-brand">
          <Logo />
          {isAssistantPage && (
            <button
              type="button"
              className="back-home-btn"
              onClick={() => navigate('/dashboard')}
              aria-label="Back to Home"
              title="Back to Home"
            >
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              <span>Back to Home</span>
            </button>
          )}
        </div>
        <form className="search" onSubmit={(event) => event.preventDefault()}>
          <Icon name="search" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search jobs, candidates, messages..."
            aria-label="Search jobs, candidates, messages"
          />
          <kbd>⌘K</kbd>
        </form>
        <div className="top-actions">
          <NotificationBell />
          <button type="button" className="icon-btn" onClick={toggle} aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}>
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
          <NavLink to="/assistant" className="ask-btn">
            <Icon name="spark" size={15} />
            Ask Mitra
          </NavLink>
          <span className="me">
            <Avatar name={userName || 'You'} size={34} />
            <span className="online" />
          </span>
        </div>
      </header>

      <div className="shell-body">
        {!isAssistantPage && (
          <aside className="sidebar">
            <NavGroup label="Workspace" items={NAV.workspace} collapsed={collapsed} counts={counts} />
            <NavGroup label="Inbox" items={NAV.inbox} collapsed={collapsed} counts={counts} />
            <NavGroup label="AI" items={NAV.ai} collapsed={collapsed} counts={counts} />
            <div className="side-foot">
              <button type="button" className="collapse-btn" onClick={() => setCollapsed((value) => !value)}>
                <Icon name="chevron" size={16} />
                {collapsed ? null : 'Collapse'}
              </button>
            </div>
          </aside>
        )}
        <main className={`main ${isAssistantPage ? 'main-assistant' : ''}`}>{children}</main>
      </div>
    </div>
  )
}
