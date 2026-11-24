import { useEffect, useState } from 'react'
import { listMyApplications } from '../services/candidatePortal'

export default function CandidateApplicationsPage() {
  const [apps, setApps] = useState([])
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    listMyApplications().then((rows) => active && setApps(Array.isArray(rows) ? rows : [])).catch((e) => active && setError(e.message))
    return () => { active = false }
  }, [])

  return (
    <div className="page np" style={{ padding: 24 }}>
      <h1 className="page-title">My Applications</h1>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {apps.map((a) => (
          <div key={a.id} className="card card-pad">
            <h3>{a.job_title}</h3>
            <p className="muted">{a.job_company} · {a.job_location}</p>
            <p><strong>Status:</strong> {({ applied: 'Applied', under_review: 'Under Review', shortlisted: 'Shortlisted', rejected: 'Rejected', interview: 'Interview', hired: 'Hired', withdrawn: 'Withdrawn' })[a.status] || a.status}</p>
            <p><strong>Applied:</strong> {a.applied_at}</p>
          </div>
        ))}
        {apps.length === 0 && <p className="muted">No applications yet.</p>}
      </div>
    </div>
  )
}
