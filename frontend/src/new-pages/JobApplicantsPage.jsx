import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { listApplicants, updateApplicationStatus } from '../services/applications'

export default function JobApplicantsPage() {
  const { jobId } = useParams()
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')

  useEffect(() => {
    let active = true
    listApplicants(jobId).then((r) => active && setRows(Array.isArray(r) ? r : [])).catch((e) => active && setError(e.message))
    return () => { active = false }
  }, [jobId])

  async function setStatus(id, status) {
    try {
      const updated = await updateApplicationStatus(id, status)
      setRows((prev) => prev.map((r) => (r.id === id ? { ...r, status: updated.status } : r)))
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="page np" style={{ padding: 24 }}>
      <h1 className="page-title">Applicants</h1>
      <p className="muted">Total applicants: {rows.length}</p>
      <div style={{ margin: '8px 0' }}>
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">All statuses</option>
          <option value="applied">Applied</option>
          <option value="under_review">Under Review</option>
          <option value="shortlisted">Shortlisted</option>
          <option value="rejected">Rejected</option>
          <option value="interview">Interview</option>
          <option value="hired">Hired</option>
        </select>
      </div>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {rows.filter((r) => filter === 'all' || r.status === filter).map((r) => (
          <div key={r.id} className="card card-pad">
            <h3>{r.candidate_name}</h3>
            <p className="muted">{r.candidate_email} · {r.candidate_phone || '—'}</p>
            <p><strong>Status:</strong> {r.status}</p>
            <p><strong>Applied:</strong> {r.applied_at}</p>
            <p><strong>Skills:</strong> {(r.candidate_skills || []).join(', ') || '—'}</p>
            <p style={{ whiteSpace: 'pre-wrap' }}>{r.candidate_resume || 'No resume text'}</p>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button className="btn btn-secondary" onClick={() => setStatus(r.id, 'shortlisted')}>Shortlist</button>
              <button className="btn btn-secondary" onClick={() => setStatus(r.id, 'rejected')}>Reject</button>
              <button className="btn btn-secondary" onClick={() => setStatus(r.id, 'interview')}>Interview</button>
              <button className="btn btn-secondary" onClick={() => setStatus(r.id, 'hired')}>Hire</button>
            </div>
          </div>
        ))}
        {rows.length === 0 && <p className="muted">No applicants yet.</p>}
      </div>
    </div>
  )
}
