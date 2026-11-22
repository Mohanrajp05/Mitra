import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Shell from '../../mitra/Shell'
import { getJob } from '../../services/jobs'
import { ApiError } from '../../services/api'

export default function JobDetailPage() {
  const { id } = useParams()
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const row = await getJob(id)
        if (!cancelled) setJob(row)
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof ApiError && err.status === 404 ? 'That job no longer exists.' : err.message || 'Could not load this job.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [id])

  return (
    <Shell>
      <p className="crumbs">
        <Link to="/jobs">Jobs</Link> / <span>{job ? job.title : 'Job'}</span>
      </p>

      {loading ? (
        <section className="card">
          <p className="muted" style={{ padding: '24px 0', textAlign: 'center' }}>Loading job…</p>
        </section>
      ) : error ? (
        <section className="card">
          <p className="muted" style={{ padding: '24px 0', textAlign: 'center', color: 'var(--danger)' }}>{error}</p>
          <div style={{ textAlign: 'center', paddingBottom: 24 }}>
            <Link to="/jobs" className="outline-btn">Back to jobs</Link>
          </div>
        </section>
      ) : job ? (
        <>
          <section className="card detail-hero">
            <div>
              <h1>{job.title}</h1>
              <p className="sub">
                {job.company ? `${job.company} · ` : ''}
                {job.location || 'Location open'} · {job.experience_required ?? 0} yrs required · Created{' '}
                {job.created_at ? new Date(job.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' }) : 'recently'}
              </p>
            </div>
            <span className={`status ${job.status === 'open' ? 'open' : 'closed'}`}>{job.status === 'open' ? 'Open' : 'Closed'}</span>
          </section>

          <div className="detail-grid">
            <section>
              <article className="card prose">
                <h2>About the role</h2>
                {job.description
                  ? job.description.split(/\n{2,}|\r\n\r\n/).map((para, index) => <p key={index}>{para}</p>)
                  : <p>No description was provided for this role yet.</p>}
              </article>

              <article className="card prose">
                <h2>Matches</h2>
                <p>Mitra scores candidates against the required skills below. Review them on the matches page.</p>
                <Link to="/matches" className="primary-btn">Open matches</Link>
              </article>
            </section>

            <aside className="detail-side">
              <section className="card">
                <h2>Required skills</h2>
                {(job.required_skills || []).length === 0 ? (
                  <p className="muted">No skills were parsed for this role.</p>
                ) : (
                  <div className="tags">
                    {(job.required_skills || []).map((skill) => (
                      <span key={skill} className="skill">{skill}</span>
                    ))}
                  </div>
                )}
                <div className="mini-stats">
                  <div><span>Experience</span><strong>{job.experience_required != null ? `${job.experience_required} yrs` : '—'}</strong></div>
                  <div><span>Location</span><strong>{job.location || 'Open'}</strong></div>
                </div>
              </section>
            </aside>
          </div>
        </>
      ) : null}
    </Shell>
  )
}
