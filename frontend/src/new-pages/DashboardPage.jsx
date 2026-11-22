import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import { getCurrentUser } from '../services/auth'
import { listCandidates } from '../services/candidates'
import { listJobs } from '../services/jobs'
import { listDocuments } from '../services/rag'
import { listChatSessions } from '../services/chat'
import { ApiError } from '../services/api'
import { sessionTimeLabel } from '../utils/chat'

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function todayLabel() {
  return new Date()
    .toLocaleDateString([], { weekday: 'long', day: 'numeric', month: 'short' })
    .toUpperCase()
}

function daysAgo(value) {
  if (!value) return 'recently'
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  return new Date(value).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

const BANDS = [
  { key: 'entry', label: 'Entry · ≤2 yrs' },
  { key: 'mid', label: 'Mid · 3–5 yrs' },
  { key: 'senior', label: 'Senior · 6–9 yrs' },
  { key: 'lead', label: 'Lead · 10+ yrs' },
]

function bandKeyForYears(years) {
  const y = Number(years)
  const safe = Number.isFinite(y) ? Math.max(0, y) : 0
  if (safe <= 2) return 'entry'
  if (safe <= 5) return 'mid'
  if (safe <= 9) return 'senior'
  return 'lead'
}

function formatYears(years) {
  const y = Number(years)
  const safe = Number.isFinite(y) ? Math.max(0, y) : 0
  const rounded = Number.isInteger(safe) ? safe : Math.round(safe * 10) / 10
  return `${rounded} ${rounded === 1 ? 'year' : 'years'}`
}

const DONUT_RADIUS = 46
const DONUT_STROKE = 14

function ExperienceDonut({ rows, total }) {
  const [hoveredKey, setHoveredKey] = useState(null)
  let offset = 0
  const segments = rows
    .filter((row) => row.count > 0)
    .map((row) => {
      const share = total > 0 ? row.count / total : 0
      const segment = { ...row, share, offset }
      offset += share
      return segment
    })

  const hoveredRow = hoveredKey ? rows.find((row) => row.key === hoveredKey) : null

  return (
    <div className="db-donut-wrap" onMouseLeave={() => setHoveredKey(null)}>
      <div className="db-donut">
        <svg
          viewBox="0 0 120 120"
          role="img"
          aria-label={`Candidates by experience: ${rows.map((row) => `${row.label} ${row.count}`).join(', ')}`}
        >
          <circle
            className="db-donut-track"
            cx="60"
            cy="60"
            r={DONUT_RADIUS}
            fill="none"
            strokeWidth={DONUT_STROKE}
          />
          {segments.map((row) => (
            <circle
              key={row.key}
              className={`db-donut-seg${hoveredKey === row.key ? ' is-hovered' : ''}`}
              data-band={row.key}
              cx="60"
              cy="60"
              r={DONUT_RADIUS}
              fill="none"
              strokeWidth={DONUT_STROKE}
              pathLength="100"
              strokeDasharray={`${row.share * 100} ${100 - row.share * 100}`}
              strokeDashoffset={-row.offset * 100}
              transform="rotate(-90 60 60)"
              tabIndex={0}
              onMouseEnter={() => setHoveredKey(row.key)}
              onFocus={() => setHoveredKey(row.key)}
              onBlur={() => setHoveredKey((current) => (current === row.key ? null : current))}
            >
              <title>{`${row.label}: ${row.count} ${row.count === 1 ? 'candidate' : 'candidates'}`}</title>
            </circle>
          ))}
        </svg>
        <div className="db-donut-center">
          <strong>{total}</strong>
          <span>{total === 1 ? 'candidate' : 'candidates'}</span>
        </div>
      </div>
      <ul className="db-donut-legend" aria-label="Experience categories">
        {rows.map((row) => (
          <li
            key={row.key}
            className={hoveredKey === row.key ? 'is-hovered' : ''}
            tabIndex={0}
            onMouseEnter={() => setHoveredKey(row.key)}
            onFocus={() => setHoveredKey(row.key)}
            onBlur={() => setHoveredKey((current) => (current === row.key ? null : current))}
          >
            <span className="db-donut-dot" data-band={row.key} aria-hidden="true" />
            <span className="db-donut-name">{row.label}</span>
          </li>
        ))}
      </ul>
      {hoveredRow && (
        <div className="db-donut-tooltip" role="tooltip">
          <div className="db-donut-tooltip-head">
            <span className="db-donut-dot" data-band={hoveredRow.key} aria-hidden="true" />
            <strong>
              {hoveredRow.label} — {hoveredRow.count} {hoveredRow.count === 1 ? 'Candidate' : 'Candidates'}
            </strong>
          </div>
          {hoveredRow.candidates.length === 0 ? (
            <p className="db-donut-tooltip-empty">No candidates in this category</p>
          ) : (
            <ul className="db-donut-tooltip-list">
              {hoveredRow.candidates.map((candidate, index) => (
                <li key={candidate.id || index}>
                  <div className="db-donut-tooltip-name">{candidate.full_name || 'Unnamed candidate'}</div>
                  <div className="db-donut-tooltip-meta">Experience: {formatYears(candidate.experience_years)}</div>
                  {(candidate.skills || []).length > 0 && (
                    <div className="db-donut-tooltip-meta">
                      Primary skills: {(candidate.skills || []).join(', ')}
                    </div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

const statusChip = { open: 'chip-green', closed: 'chip-gray' }

export default function DashboardPage() {
  const [userName, setUserName] = useState('there')
  const [jobs, setJobs] = useState([])
  const [candidates, setCandidates] = useState([])
  const [documents, setDocuments] = useState([])
  const [sessions, setSessions] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    getCurrentUser()
      .then((user) => {
        if (cancelled) return
        const meta = user?.user_metadata || {}
        setUserName(meta.full_name || meta.name || (user?.email || '').split('@')[0] || 'there')
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const [jobRows, candidateRows, documentData, sessionRows] = await Promise.all([
          listJobs(),
          listCandidates(),
          listDocuments(),
          listChatSessions().catch(() => []),
        ])
        if (cancelled) return
        setJobs(Array.isArray(jobRows) ? jobRows : [])
        setCandidates(Array.isArray(candidateRows) ? candidateRows : [])
        setDocuments(documentData.documents || [])
        setSessions(Array.isArray(sessionRows) ? sessionRows : [])
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load dashboard data.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const openJobs = jobs.filter((job) => job.status === 'open')
  const resumeDocs = documents.filter((doc) => doc.source_type === 'resume')
  const jobDocs = documents.filter((doc) => doc.source_type === 'job_description')

  const stats = [
    { key: 'jobs', label: 'Active jobs', value: openJobs.length, note: `${jobs.length} total roles`, icon: 'briefcase', tone: 'indigo' },
    { key: 'candidates', label: 'Candidates', value: candidates.length, note: `${candidates.filter((c) => (c.experience_years || 0) > 5).length} with 6+ yrs experience`, icon: 'users', tone: 'violet' },
    { key: 'resumes', label: 'Resumes indexed', value: resumeDocs.length, note: `${jobDocs.length} job descriptions`, icon: 'file', tone: 'green' },
    { key: 'chats', label: 'Conversations', value: sessions.length, note: 'with the AI assistant', icon: 'message', tone: 'blue' },
  ]

  const suggestions = useMemo(() => {
    const items = []
    const latestJob = [...jobs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
    if (jobs.length === 0) {
      items.push({ id: 's0', icon: 'plus', tone: 'indigo', title: 'Create your first job', detail: 'Describe the role and Mitra will structure it for matching.', to: '/jobs/new', action: 'New job', primary: true })
    }
    if (documents.length === 0) {
      items.push({ id: 's1', icon: 'upload', tone: 'coral', title: 'Upload resumes to start matching', detail: 'Open a candidate profile to upload, parse and index their resume.', to: '/candidates', action: 'View candidates', primary: true })
    }
    if (latestJob) {
      items.push({ id: 's2', icon: 'target', tone: 'violet', title: `Review matches for ${latestJob.title}`, detail: 'Compare candidates requirement by requirement.', to: '/matches', action: 'Open matches', primary: true })
      items.push({ id: 's3', icon: 'sparkle', tone: 'green', title: `Run job analysis on ${latestJob.title}`, detail: 'Extract skills, seniority and interview focus areas.', to: '/assistant/workspace', action: 'Analyze', primary: false })
    }
    if (sessions.length === 0) {
      items.push({ id: 's4', icon: 'message', tone: 'blue', title: 'Ask Mitra about your talent pool', detail: 'Every answer cites the resume it came from.', to: '/assistant', action: 'Open chat', primary: false })
    }
    return items.slice(0, 4)
  }, [jobs, documents, sessions])

  const experienceRows = useMemo(() => {
    const grouped = { entry: [], mid: [], senior: [], lead: [] }
    candidates.forEach((candidate) => {
      const key = bandKeyForYears(candidate.experience_years)
      if (!grouped[key]) grouped[key] = []
      grouped[key].push(candidate)
    })
    return BANDS.map((band) => ({
      ...band,
      candidates: grouped[band.key] || [],
      count: (grouped[band.key] || []).length,
    }))
  }, [candidates])

  const recentJobs = useMemo(
    () => [...jobs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at)).slice(0, 4),
    [jobs],
  )

  const recentCandidates = useMemo(
    () => [...candidates]
      .sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))
      .slice(0, 5),
    [candidates],
  )

  const activity = useMemo(() => {
    const items = []
    const latestSession = [...sessions].sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0))[0]
    if (latestSession) {
      items.push({ id: 'a1', agent: 'Assistant', text: `Conversation “${latestSession.title || 'New chat'}” updated`, time: sessionTimeLabel(latestSession.updated_at), tone: 'indigo', at: new Date(latestSession.updated_at || 0).getTime() })
    }
    const latestDoc = [...documents].sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0))[0]
    if (latestDoc) {
      items.push({ id: 'a2', agent: 'Parser', text: `Indexed “${latestDoc.filename}”`, time: daysAgo(latestDoc.created_at), tone: 'green', at: new Date(latestDoc.created_at || 0).getTime() })
    }
    const latestJob = [...jobs].sort((a, b) => new Date(b.created_at) - new Date(a.created_at))[0]
    if (latestJob) {
      items.push({ id: 'a3', agent: 'Jobs', text: `Created role “${latestJob.title}”`, time: daysAgo(latestJob.created_at), tone: 'coral', at: new Date(latestJob.created_at).getTime() })
    }
    return items.sort((a, b) => b.at - a.at).slice(0, 4)
  }, [sessions, documents, jobs])

  function refresh() {
    setReloadKey((key) => key + 1)
  }

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">{todayLabel()}</div>
          <h1 className="page-title">
            {greeting()}, {userName} <span aria-hidden="true">🌙</span>
          </h1>
          <p className="page-sub">Live numbers from your workspace: jobs, candidates and the AI assistant.</p>
        </div>
        <div className="page-actions">
          <Link to="/candidates" className="btn btn-secondary">
            <NwIcon name="upload" /> Manage resumes
          </Link>
          <Link to="/jobs/new" className="btn btn-primary">
            <NwIcon name="plus" /> New job
          </Link>
        </div>
      </header>

      {error && (
        <section className="card card-pad" role="alert">
          <p className="muted" style={{ color: 'var(--danger)' }}>{error}</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
            <NwIcon name="refresh" /> Try again
          </button>
        </section>
      )}

      {loading ? (
        <section className="card card-pad" style={{ textAlign: 'center', padding: 64 }}>
          <p className="muted">Loading your workspace…</p>
        </section>
      ) : (
        <>
          <section className="stat-grid" aria-label="Key numbers">
            {stats.map((stat) => (
              <article key={stat.key} className="card stat-card">
                <div className="stat-top">
                  <span className="muted">{stat.label}</span>
                  <span className={`tile tile-${stat.tone}`}>
                    <NwIcon name={stat.icon} />
                  </span>
                </div>
                <div className="stat-value">{stat.value}</div>
                <div className="stat-foot">
                  <span className="muted">{stat.note}</span>
                </div>
              </article>
            ))}
          </section>

          <div className="dash-grid">
            <div className="dash-main">
              <section className="card suggest-card" aria-label="Mitra suggestions">
                <div className="card-head">
                  <span className="ai-badge"><NwIcon name="sparkle" /> Mitra suggests</span>
                  <button type="button" className="link refresh" onClick={refresh}>
                    <NwIcon name="refresh" /> Refresh
                  </button>
                </div>
                <h2 className="suggest-title">Here’s what I’d focus on today</h2>
                {suggestions.length === 0 ? (
                  <p className="muted">Nothing needs attention right now.</p>
                ) : (
                  <ul className="suggest-list">
                    {suggestions.map((item) => (
                      <li key={item.id} className="suggest-item">
                        <span className={`tile tile-${item.tone}`}><NwIcon name={item.icon} /></span>
                        <div className="suggest-text">
                          <strong>{item.title}</strong>
                          <span>{item.detail}</span>
                        </div>
                        <Link to={item.to} className={`btn btn-sm ${item.primary ? 'btn-primary' : 'btn-secondary'}`}>
                          {item.action}
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="card card-pad" aria-label="Candidate experience mix">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Talent pool</div>
                    <h2 className="card-title">Candidates · by experience</h2>
                  </div>
                </div>
                {candidates.length === 0 ? (
                  <p className="muted db-donut-empty">No candidates yet. Upload resumes to fill your pipeline.</p>
                ) : (
                  <ExperienceDonut rows={experienceRows} total={candidates.length} />
                )}
                <div className="funnel-summary">
                  <span><strong>{candidates.length}</strong> candidates</span>
                  <span><strong>{candidates.filter((c) => (c.skills || []).length > 0).length}</strong> with parsed skills</span>
                  <span><strong>{resumeDocs.length}</strong> resumes indexed</span>
                </div>
              </section>

              <section className="card card-pad" aria-label="Recent jobs">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Recent jobs</div>
                    <h2 className="card-title">Roles you’re hiring for</h2>
                  </div>
                  <Link to="/jobs" className="link">View all</Link>
                </div>
                {recentJobs.length === 0 ? (
                  <p className="muted">No jobs yet. <Link to="/jobs/new" className="link">Create your first role</Link>.</p>
                ) : (
                  <ul className="job-rows">
                    {recentJobs.map((job) => (
                      <li key={job.id}>
                        <Link to={`/jobs/${job.id}`} className="job-row">
                          <span className={`tile tile-${job.status === 'open' ? 'indigo' : 'gray'}`}><NwIcon name="briefcase" /></span>
                          <div className="job-row-main">
                            <strong>{job.title}</strong>
                            <span className="muted">{job.location || 'Location open'} · {job.required_skills.length} skills · Posted {daysAgo(job.created_at)}</span>
                          </div>
                          <div className="job-row-count">
                            <strong>{job.experience_required == null
                              ? '—'
                              : `${job.experience_required} ${Number(job.experience_required) === 1 ? 'year' : 'years'} required`}</strong>
                          </div>
                          <span className={`chip ${statusChip[job.status] || 'chip-gray'}`}>
                            <span className="dot" /> {job.status === 'open' ? 'Open' : 'Closed'}
                          </span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <aside className="dash-side">
              <section className="card card-pad" aria-label="Upcoming interviews">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Upcoming</div>
                    <h2 className="card-title">Interviews</h2>
                  </div>
                  <Link to="/interviews" className="link">Calendar</Link>
                </div>
                <p className="muted">
                  No interviews scheduled yet. Pick suggested slots on the <Link to="/interviews" className="link">interviews calendar</Link>.
                </p>
              </section>

              <section className="card card-pad" aria-label="Recently added candidates">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Recently added</div>
                    <h2 className="card-title">Candidates</h2>
                  </div>
                  <Link to="/candidates" className="link">View all</Link>
                </div>
                {recentCandidates.length === 0 ? (
                  <p className="muted">No candidates in your talent pool yet.</p>
                ) : (
                  <ul className="cand-list">
                    {recentCandidates.map((candidate) => (
                      <li key={candidate.id}>
                        <Avatar name={candidate.full_name} size={34} />
                        <div className="cand-main">
                          <strong>{candidate.full_name}</strong>
                          <span className="muted">
                            {candidate.experience_years ?? 0} yrs · {candidate.education || 'Education n/a'}
                          </span>
                        </div>
                        <span className="score-pill">{candidate.experience_years ?? 0} yrs</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="card card-pad" aria-label="Recent activity">
                <div className="eyebrow" style={{ marginBottom: 10 }}>Recent activity</div>
                {activity.length === 0 ? (
                  <p className="muted">No activity yet. Create a job or upload a resume to get started.</p>
                ) : (
                  <ul className="activity">
                    {activity.map((item) => (
                      <li key={item.id}>
                        <span className={`act-dot act-${item.tone}`} />
                        <span className="act-text">
                          <strong>{item.agent}</strong> {item.text}
                        </span>
                        <span className="act-time muted">{item.time}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
