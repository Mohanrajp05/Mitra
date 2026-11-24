import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import NwIcon from './NwIcon'
import { getCandidateDashboard, onboardCandidate } from '../services/candidatePortal'
import { getCurrentUser } from '../services/auth'

const STATUS_LABELS = {
  applied: 'Applied',
  under_review: 'Under review',
  shortlisted: 'Shortlisted',
  rejected: 'Rejected',
  interview: 'Interview',
  hired: 'Hired',
  withdrawn: 'Withdrawn',
}

function greeting() {
  const hour = new Date().getHours()
  if (hour < 12) return 'Good morning'
  if (hour < 17) return 'Good afternoon'
  return 'Good evening'
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatDateTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function CandidateDashboardPage() {
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let active = true
    async function load() {
      setLoading(true)
      try {
        let data = await getCandidateDashboard()
        // If email confirmation interrupted the original onboarding, the role
        // is recovered from the verified signup metadata but the profile row
        // may still be missing. Finish onboarding once, then reload stats.
        if (data && data.profile === null) {
          try {
            const user = await getCurrentUser()
            const meta = user?.user_metadata || {}
            const fullName = meta.full_name || meta.name
            if (fullName) {
              await onboardCandidate({ full_name: fullName, email: user?.email })
              data = await getCandidateDashboard()
            }
          } catch {
            // The dashboard still renders with a zero-completion state.
          }
        }
        if (active) setDashboard(data)
      } catch (e) {
        if (active) setError(e.message)
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  const profile = dashboard?.profile
  const stats = dashboard?.stats || {}
  const applications = dashboard?.recent_applications || []
  const interviews = dashboard?.upcoming_interviews || []
  const messages = dashboard?.recent_messages || []
  const displayName = profile?.full_name || 'there'

  const cards = [
    { key: 'applied', label: 'Jobs applied', value: stats.total_applications ?? 0, note: 'total applications', icon: 'briefcase', tone: 'indigo' },
    { key: 'review', label: 'Under review', value: stats.under_review ?? 0, note: 'being reviewed', icon: 'search', tone: 'amber' },
    { key: 'shortlisted', label: 'Shortlisted', value: stats.shortlisted ?? 0, note: 'moved forward', icon: 'target', tone: 'green' },
    { key: 'interviews', label: 'Upcoming interviews', value: stats.upcoming_interviews ?? 0, note: 'scheduled', icon: 'calendar', tone: 'blue' },
  ]

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Candidate dashboard</div>
          <h1 className="page-title">{greeting()}, {displayName}</h1>
          <p className="page-sub">Track your applications, interviews and recruiter conversations in one place.</p>
        </div>
        <div className="page-actions">
          <Link to="/candidate/jobs" className="btn btn-primary">
            <NwIcon name="briefcase" /> Browse jobs
          </Link>
        </div>
      </header>

      {error && (
        <section className="card card-pad" role="alert" style={{ marginBottom: 18 }}>
          <p style={{ color: 'var(--danger)' }}>{error}</p>
        </section>
      )}

      {loading ? (
        <section className="card card-pad" style={{ textAlign: 'center', padding: 48 }}>
          <p className="muted">Loading your dashboard…</p>
        </section>
      ) : (
        <>
          <section className="stat-grid" aria-label="Application summary">
            {cards.map((card) => (
              <article key={card.key} className="card stat-card">
                <div className="stat-top">
                  <span className="muted">{card.label}</span>
                  <span className={`tile tile-${card.tone}`}><NwIcon name={card.icon} /></span>
                </div>
                <div className="stat-value">{card.value}</div>
                <div className="stat-foot"><span className="muted">{card.note}</span></div>
              </article>
            ))}
          </section>

          <div className="dash-grid">
            <div className="dash-main">
              <section className="card card-pad" aria-label="Profile status">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Your profile</div>
                    <h2 className="card-title">Application readiness</h2>
                  </div>
                  <Link to="/candidate/profile" className="link">View profile</Link>
                </div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'center' }}>
                  <div>
                    <div style={{ fontSize: 34, fontWeight: 700 }}>{dashboard?.profile_completion ?? 0}%</div>
                    <div className="muted" style={{ fontSize: 12 }}>profile complete</div>
                  </div>
                  <div style={{ flex: 1, minWidth: 200 }}>
                    <div
                      role="progressbar"
                      aria-valuenow={dashboard?.profile_completion ?? 0}
                      aria-valuemin={0}
                      aria-valuemax={100}
                      style={{ height: 8, borderRadius: 999, background: 'var(--surface-2)', overflow: 'hidden' }}
                    >
                      <div
                        style={{
                          width: `${Math.min(100, Math.max(0, dashboard?.profile_completion ?? 0))}%`,
                          height: '100%',
                          background: 'var(--primary)',
                        }}
                      />
                    </div>
                    <p style={{ marginTop: 12, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span className={`chip ${dashboard?.has_resume ? 'chip-green' : 'chip-amber'}`}>
                        <span className="dot" /> {dashboard?.has_resume ? 'Resume on file' : 'Resume missing'}
                      </span>
                      <Link to="/candidate/resume" className="link">
                        {dashboard?.has_resume ? 'Update resume' : 'Add your resume'}
                      </Link>
                    </p>
                  </div>
                </div>
              </section>

              <section className="card card-pad" aria-label="Recent applications">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Applications</div>
                    <h2 className="card-title">Recent activity</h2>
                  </div>
                  <Link to="/candidate/applications" className="link">View all</Link>
                </div>
                {applications.length === 0 ? (
                  <p className="muted">No applications yet. <Link to="/candidate/jobs" className="link">Browse open jobs</Link>.</p>
                ) : (
                  <ul className="job-rows">
                    {applications.map((application) => (
                      <li key={application.id}>
                        <div className="job-row">
                          <span className="tile tile-indigo"><NwIcon name="briefcase" /></span>
                          <div className="job-row-main">
                            <strong>{application.job_title || 'Role'}</strong>
                            <span className="muted">
                              {application.job_company || 'Company'} · {application.job_location || 'Location open'}
                            </span>
                          </div>
                          <div className="job-row-count">
                            <strong>{formatDate(application.applied_at)}</strong>
                            <span className="muted">applied</span>
                          </div>
                          <span className={`chip ${application.status === 'shortlisted' ? 'chip-green' : application.status === 'rejected' ? 'chip-coral' : 'chip-gray'}`}>
                            <span className="dot" /> {STATUS_LABELS[application.status] || application.status}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="card card-pad" aria-label="Upcoming interviews">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Interviews</div>
                    <h2 className="card-title">Upcoming</h2>
                  </div>
                  <Link to="/candidate/interviews" className="link">Manage interviews</Link>
                </div>
                {interviews.length === 0 ? (
                  <p className="muted">No upcoming interviews scheduled.</p>
                ) : (
                  <ul className="int-list">
                    {interviews.map((interview) => (
                      <li key={interview.id} className="int-item">
                        <span className="date-tile">
                          <span>{new Date(interview.interview_date).toLocaleDateString([], { month: 'short' }).toUpperCase()}</span>
                          <strong>{new Date(interview.interview_date).getDate()}</strong>
                        </span>
                        <div className="int-body">
                          <div className="int-name">
                            <strong>{interview.title || 'Interview'}</strong>
                            <span className={`chip ${interview.candidate_response === 'accepted' ? 'chip-green' : interview.candidate_response === 'declined' ? 'chip-coral' : 'chip-amber'}`}>
                              {interview.candidate_response || 'awaiting response'}
                            </span>
                          </div>
                          <span className="muted">
                            {String(interview.start_time || '').slice(0, 5)} · {interview.interview_type || 'Interview'} · {interview.time_zone || 'UTC'}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <aside className="dash-side">
              <section className="card card-pad" aria-label="Recent recruiter messages">
                <div className="card-head">
                  <div>
                    <div className="eyebrow">Messages</div>
                    <h2 className="card-title">From recruiters</h2>
                  </div>
                  <Link to="/candidate/messages" className="link">Open inbox</Link>
                </div>
                {messages.length === 0 ? (
                  <p className="muted">No recruiter messages yet.</p>
                ) : (
                  <ul className="cand-list">
                    {messages.map((conversation) => (
                      <li key={conversation.id}>
                        <span className="tile tile-blue"><NwIcon name="mail" /></span>
                        <div className="cand-main">
                          <strong>{conversation.job_title || 'Conversation'}</strong>
                          <span className="muted">{conversation.last_message || 'No messages yet'}</span>
                          <span className="muted" style={{ fontSize: 11 }}>{formatDateTime(conversation.last_message_at)}</span>
                        </div>
                        {Number(conversation.unread_count) > 0 && (
                          <span className="nav-count">{conversation.unread_count}</span>
                        )}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="card card-pad" aria-label="Quick links">
                <div className="eyebrow" style={{ marginBottom: 10 }}>Quick links</div>
                <ul className="cand-list">
                  <li>
                    <span className="tile tile-indigo"><NwIcon name="briefcase" /></span>
                    <div className="cand-main"><strong><Link to="/candidate/jobs" className="link">Browse open jobs</Link></strong><span className="muted">Find your next role</span></div>
                  </li>
                  <li>
                    <span className="tile tile-green"><NwIcon name="file" /></span>
                    <div className="cand-main"><strong><Link to="/candidate/applications" className="link">My applications</Link></strong><span className="muted">Track every status</span></div>
                  </li>
                  <li>
                    <span className="tile tile-amber"><NwIcon name="calendar" /></span>
                    <div className="cand-main"><strong><Link to="/candidate/interviews" className="link">My interviews</Link></strong><span className="muted">Respond to invitations</span></div>
                  </li>
                </ul>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  )
}
