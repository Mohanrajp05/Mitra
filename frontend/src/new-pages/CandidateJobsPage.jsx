import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { listCandidateJobs, applyToJob } from '../services/candidatePortal'

const EXPERIENCE_LEVELS = ['Fresher', 'Internship', 'Experienced']
const JOB_TYPES = ['Full-time', 'Part-time', 'Internship', 'Contract']
const DURATIONS = ['1', '3', '6', '12']
const COMPENSATIONS = ['Paid', 'Unpaid', 'Stipend']
const WORK_MODES = ['Remote', 'Hybrid', 'On-site']

const emptyFilters = {
  role: '',
  experience: '',
  jobType: '',
  duration: '',
  compensation: '',
  workMode: '',
  location: '',
}

export default function CandidateJobsPage() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(emptyFilters)

  useEffect(() => {
    let active = true
    listCandidateJobs()
      .then((rows) => active && setJobs(Array.isArray(rows) ? rows : []))
      .catch((e) => active && setError(e.message))
    return () => { active = false }
  }, [])

  function setFilter(key, value) {
    setFilters((f) => ({ ...f, [key]: value }))
  }

  function clearFilters() {
    setFilters(emptyFilters)
    setQuery('')
  }

  async function apply(jobId) {
    setBusy(jobId); setError('')
    try { await applyToJob(jobId); alert('Applied successfully') }
    catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return jobs.filter((job) => {
      const matchesQuery = !q ||
        (job.title || '').toLowerCase().includes(q) ||
        (job.company || '').toLowerCase().includes(q) ||
        (job.description || '').toLowerCase().includes(q) ||
        (job.required_skills || []).some((s) => String(s).toLowerCase().includes(q))
      if (!matchesQuery) return false

      if (filters.role && !(job.title || '').toLowerCase().includes(filters.role.toLowerCase())) return false
      if (filters.experience && job.experience_level !== filters.experience) return false
      if (filters.jobType && job.job_type !== filters.jobType) return false
      if (filters.duration && String(job.internship_duration_months) !== filters.duration) return false
      if (filters.compensation && job.compensation_type !== filters.compensation) return false
      if (filters.workMode && job.work_mode !== filters.workMode) return false
      if (filters.location) {
        const loc = (job.location || '').toLowerCase()
        const mode = (job.work_mode || '').toLowerCase()
        const needle = filters.location.toLowerCase()
        if (!loc.includes(needle) && !mode.includes(needle)) return false
      }
      return true
    })
  }, [jobs, query, filters])

  const hasActiveFilters = query.trim() || Object.values(filters).some(Boolean)

  return (
    <div className="page np" style={{ padding: 24 }}>
      <h1 className="page-title">Browse Jobs</h1>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}

      <div className="card card-pad" style={{ marginTop: 12 }}>
        <input className="input" placeholder="Search by title, company, skills…" value={query} onChange={(e) => setQuery(e.target.value)} style={{ width: '100%' }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8, marginTop: 10 }}>
          <select className="input" value={filters.role} onChange={(e) => setFilter('role', e.target.value)}>
            <option value="">All roles</option>
            {['Python Developer','Full Stack Developer','Frontend Developer','Backend Developer','AI/ML Engineer','Data Analyst','Java Developer'].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
          <select className="input" value={filters.experience} onChange={(e) => setFilter('experience', e.target.value)}>
            <option value="">Experience level</option>
            {EXPERIENCE_LEVELS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={filters.jobType} onChange={(e) => setFilter('jobType', e.target.value)}>
            <option value="">Job type</option>
            {JOB_TYPES.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={filters.duration} onChange={(e) => setFilter('duration', e.target.value)}>
            <option value="">Internship duration</option>
            {DURATIONS.map((v) => <option key={v} value={v}>{v} month{v === '1' ? '' : 's'}</option>)}
          </select>
          <select className="input" value={filters.compensation} onChange={(e) => setFilter('compensation', e.target.value)}>
            <option value="">Compensation</option>
            {COMPENSATIONS.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <select className="input" value={filters.workMode} onChange={(e) => setFilter('workMode', e.target.value)}>
            <option value="">Work mode</option>
            {WORK_MODES.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <input className="input" placeholder="Location" value={filters.location} onChange={(e) => setFilter('location', e.target.value)} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 10 }}>
          <span className="muted">{filtered.length} job{filtered.length === 1 ? '' : 's'} found</span>
          {hasActiveFilters && <button type="button" className="btn btn-secondary" onClick={clearFilters}>Clear filters</button>}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {filtered.length === 0 && (
          <div className="card card-pad" style={{ textAlign: 'center' }}>
            <p className="muted">No jobs match your search. Try adjusting the filters.</p>
          </div>
        )}
        {filtered.map((job) => (
          <div key={job.id} className="card card-pad">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
              <div style={{ minWidth: 0 }}>
                <h3 style={{ margin: 0 }}>{job.title}</h3>
                <p className="muted" style={{ margin: '4px 0' }}>{job.company || '—'} · {job.location || '—'}</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, margin: '6px 0' }}>
                  {job.job_type && <span className="chip chip-indigo">{job.job_type}</span>}
                  {job.experience_level && <span className="chip chip-indigo">{job.experience_level}</span>}
                  {job.work_mode && <span className="chip chip-indigo">{job.work_mode}</span>}
                  {job.compensation_type && <span className="chip chip-green">{job.compensation_type}{job.salary_stipend ? ` · ${job.salary_stipend}` : ''}</span>}
                  {job.internship_duration_months && <span className="chip chip-amber">{job.internship_duration_months} month internship</span>}
                </div>
                {(job.required_skills || []).length > 0 && (
                  <p className="muted" style={{ margin: '4px 0', fontSize: 13 }}>
                    Skills: {(job.required_skills || []).slice(0, 6).join(', ')}
                  </p>
                )}
                <p style={{ margin: '6px 0', fontSize: 14 }}>{(job.description || '').slice(0, 160)}{(job.description || '').length > 160 ? '…' : ''}</p>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, flexShrink: 0 }}>
                <button className="btn btn-secondary" onClick={() => navigate(`/candidate/jobs/${job.id}`)}>View Details</button>
                <button className="btn btn-primary" disabled={busy === job.id} onClick={() => apply(job.id)}>
                  {busy === job.id ? 'Applying…' : 'Apply Now'}
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}