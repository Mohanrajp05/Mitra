import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getCandidateJob, applyToJob } from '../services/candidatePortal'

export default function CandidateJobDetailPage() {
  const { jobId } = useParams()
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    let active = true
    getCandidateJob(jobId).then((j) => active && setJob(j)).catch((e) => active && setError(e.message))
    return () => { active = false }
  }, [jobId])

  async function apply() {
    setBusy(true); setError('')
    try { await applyToJob(jobId); alert('Applied successfully') }
    catch (e) { setError(e.message) }
    finally { setBusy(false) }
  }

  if (!job) return <div style={{ padding: 24 }}>Loading…</div>
  const docs = Array.isArray(job.required_documents) ? job.required_documents : []
  return (
    <div className="page np" style={{ padding: 24, maxWidth: 820 }}>
      <h1 className="page-title">{job.title}</h1>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      <p className="muted">{job.company || '—'} · {job.location || '—'}</p>

      <div className="card card-pad" style={{ marginTop: 16 }}>
        <h2>About the Job</h2>
        <p style={{ whiteSpace: 'pre-wrap' }}>{job.description || '—'}</p>
      </div>

      {Array.isArray(job.required_skills) && job.required_skills.length > 0 && (
        <div className="card card-pad" style={{ marginTop: 12 }}>
          <h2>Required Skills</h2>
          <ul>{job.required_skills.map((s) => <li key={s}>{s}</li>)}</ul>
        </div>
      )}

      <div className="card card-pad" style={{ marginTop: 12 }}>
        <h2>Job Details</h2>
        <dl className="cd-facts">
          <div><dt>Experience level</dt><dd>{job.experience_level || '—'}</dd></div>
          <div><dt>Experience required</dt><dd>{job.experience_required != null ? `${job.experience_required} years` : '—'}</dd></div>
          <div><dt>Job type</dt><dd>{job.job_type || '—'}</dd></div>
          <div><dt>Internship duration</dt><dd>{job.internship_duration_months ? `${job.internship_duration_months} months` : '—'}</dd></div>
          <div><dt>Compensation</dt><dd>{job.compensation_type || '—'}{job.salary_stipend ? ` · ${job.salary_stipend}` : ''}</dd></div>
          <div><dt>Work mode</dt><dd>{job.work_mode || '—'}</dd></div>
          <div><dt>Location</dt><dd>{job.location || '—'}</dd></div>
          <div><dt>Application deadline</dt><dd>{job.application_deadline || '—'}</dd></div>
        </dl>
      </div>

      <div className="card card-pad" style={{ marginTop: 12 }}>
        <h2>Required Documents</h2>
        {docs.length === 0 ? (
          <p className="muted">Not specified by recruiter.</p>
        ) : (
          <ul>{docs.map((d) => <li key={d}>{d}</li>)}</ul>
        )}
      </div>

      <button className="btn btn-primary" style={{ marginTop: 16 }} disabled={busy} onClick={apply}>
        {busy ? 'Applying…' : 'Apply Now'}
      </button>
    </div>
  )
}