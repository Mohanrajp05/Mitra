import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import NwIcon from './NwIcon'
import { bulkDeleteJobs, deleteJob, listJobs } from '../services/jobs'
import { ApiError } from '../services/api'

const PAGE_SIZE = 8
const FILTERS = ['All', 'Open', 'Closed']
const TILE_TONES = ['indigo', 'violet', 'green', 'coral', 'blue', 'amber']

function postedLabel(value) {
  if (!value) return '—'
  const days = Math.floor((Date.now() - new Date(value).getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  return new Date(value).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

function JobsEmpty({ onCreate }) {
  const ways = [
    { icon: 'file', tone: 'indigo', title: 'Paste a job description', text: 'Drop in any JD and Mitra will structure it for you.' },
    { icon: 'target', tone: 'coral', title: 'Analyze with the AI workspace', text: 'Open the full workspace to analyze roles and draft JDs.' },
    { icon: 'users', tone: 'green', title: 'Match your talent pool', text: 'Compare saved candidates against the role, line by line.' },
  ]

  return (
    <>
      <section className="card jobs-empty">
        <svg className="empty-art" viewBox="0 0 200 150" role="img" aria-label="Illustration of an empty briefcase">
          <rect x="30" y="52" width="140" height="82" rx="12" fill="#5b52e8" />
          <rect x="78" y="38" width="44" height="22" rx="7" fill="none" stroke="#3f37b8" strokeWidth="8" />
          <rect x="30" y="86" width="140" height="10" fill="#4338ca" />
          <rect x="92" y="82" width="16" height="20" rx="4" fill="#fbbf24" />
          <rect x="52" y="14" width="46" height="30" rx="6" fill="#fff" stroke="#c7d2fe" strokeWidth="2" transform="rotate(-8 52 14)" />
          <rect x="108" y="10" width="46" height="30" rx="6" fill="#fff" stroke="#fbcfe8" strokeWidth="2" transform="rotate(7 108 10)" />
          <path d="M160 24l3 8 8 3-8 3-3 8-3-8-8-3 8-3z" fill="#f26b4f" />
        </svg>
        <h2>No jobs yet — let’s post your first role</h2>
        <p className="muted">
          Describe the role in your own words. Mitra will pull out skills, seniority and experience so you can start matching candidates right away.
        </p>
        <div className="empty-actions">
          <button type="button" className="btn btn-primary" onClick={onCreate}>
            <NwIcon name="plus" /> Create job
          </button>
          <Link to="/assistant/workspace" className="btn btn-secondary draft-btn">
            <NwIcon name="sparkle" /> Draft with Mitra
          </Link>
        </div>
      </section>

      <div className="eyebrow" style={{ margin: '24px 0 10px' }}>Other ways to start</div>
      <div className="ways-grid">
        {ways.map((way) => (
          <button key={way.title} type="button" className="card way-card" onClick={onCreate}>
            <span className={`tile tile-${way.tone}`}><NwIcon name={way.icon} /></span>
            <strong>{way.title}</strong>
            <span className="muted">{way.text}</span>
          </button>
        ))}
      </div>
    </>
  )
}

export default function JobsPage() {
  const navigate = useNavigate()
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  const [filter, setFilter] = useState('All')
  const [query, setQuery] = useState('')
  const [view, setView] = useState('grid')
  const [page, setPage] = useState(1)

  const [selectedIds, setSelectedIds] = useState([])
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const rows = await listJobs()
        if (!cancelled) setJobs(Array.isArray(rows) ? rows : [])
      } catch (err) {
        if (!cancelled) setError(err instanceof ApiError ? err.message : 'Could not load jobs.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  const counts = useMemo(
    () => ({
      All: jobs.length,
      Open: jobs.filter((job) => job.status === 'open').length,
      Closed: jobs.filter((job) => job.status === 'closed').length,
    }),
    [jobs],
  )

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    return jobs.filter((job) => {
      const statusLabel = job.status === 'open' ? 'Open' : 'Closed'
      if (filter !== 'All' && statusLabel !== filter) return false
      if (!q) return true
      return (
        (job.title || '').toLowerCase().includes(q) ||
        (job.location || '').toLowerCase().includes(q) ||
        (job.required_skills || []).some((skill) => skill.toLowerCase().includes(q))
      )
    })
  }, [jobs, filter, query])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const visible = filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)

  const allFilteredSelected =
    filtered.length > 0 && filtered.every((job) => selectedIds.includes(job.id))

  function toggleSelected(jobId) {
    setSelectedIds((ids) =>
      ids.includes(jobId) ? ids.filter((id) => id !== jobId) : [...ids, jobId],
    )
  }

  function toggleSelectAll() {
    if (allFilteredSelected) {
      setSelectedIds([])
    } else {
      setSelectedIds(filtered.map((job) => job.id))
    }
  }

  async function handleDelete(job) {
    if (busy) return
    if (!window.confirm(`Delete "${job.title}"? This cannot be undone.`)) return
    setBusy(true)
    setActionError('')
    try {
      await deleteJob(job.id)
      setJobs((rows) => rows.filter((row) => row.id !== job.id))
      setSelectedIds((ids) => ids.filter((id) => id !== job.id))
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Could not delete this job role. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  async function handleBulkDelete() {
    if (busy || selectedIds.length === 0) return
    const count = selectedIds.length
    const plural = count === 1 ? 'job role' : 'job roles'
    if (!window.confirm(`Delete ${count} selected ${plural}? This cannot be undone.`)) return
    setBusy(true)
    setActionError('')
    try {
      const result = await bulkDeleteJobs(selectedIds)
      const deleted = Number(result?.deleted ?? 0)
      if (deleted >= count) {
        setJobs((rows) => rows.filter((row) => !selectedIds.includes(row.id)))
      } else {
        setReloadKey((key) => key + 1)
        setActionError(`Deleted ${deleted} of ${count} ${plural}. The list was refreshed.`)
      }
      setSelectedIds([])
      setPage(1)
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Could not delete the selected job roles. Please try again.')
    } finally {
      setBusy(false)
    }
  }

  function resetToFirst(resetter) {
    resetter()
    setPage(1)
  }

  if (loading) {
    return (
      <div className="page np">
        <section className="card card-pad" style={{ textAlign: 'center', padding: 64 }}>
          <p className="muted">Loading jobs…</p>
        </section>
      </div>
    )
  }

  if (error) {
    return (
      <div className="page np">
        <section className="card card-pad" role="alert">
          <p className="muted" style={{ color: 'var(--danger)' }}>{error}</p>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setReloadKey((key) => key + 1)}>
            <NwIcon name="refresh" /> Try again
          </button>
        </section>
      </div>
    )
  }

  return (
    <div className="page np jobs-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">Hiring</div>
          <h1 className="page-title">Jobs</h1>
          <p className="page-sub">Every role you’re hiring for, with live counts from your workspace.</p>
        </div>
        <div className="page-actions">
          <Link to="/assistant/workspace" className="btn btn-secondary">
            <NwIcon name="download" /> Import
          </Link>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/jobs/new')}>
            <NwIcon name="plus" /> Create job
          </button>
        </div>
      </header>

      {jobs.length === 0 ? (
        <JobsEmpty onCreate={() => navigate('/jobs/new')} />
      ) : (
        <>
          <div className="jobs-toolbar">
            <div className="input-wrap jobs-search">
              <NwIcon name="search" />
              <input
                className="input"
                placeholder="Search by title, skill or location"
                value={query}
                onChange={(event) => resetToFirst(() => setQuery(event.target.value))}
                aria-label="Search jobs"
              />
            </div>

            <div className="filter-chips" role="group" aria-label="Filter by status">
              {FILTERS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`filter-chip${filter === item ? ' active' : ''}`}
                  aria-pressed={filter === item}
                  onClick={() => resetToFirst(() => setFilter(item))}
                >
                  {item} <span>{counts[item]}</span>
                </button>
              ))}
            </div>

            <div className="toolbar-right">
              <button
                type="button"
                className={`filter-chip${allFilteredSelected ? ' active' : ''}`}
                aria-pressed={allFilteredSelected}
                disabled={filtered.length === 0}
                onClick={toggleSelectAll}
                aria-label="Select all job roles"
              >
                <NwIcon name={allFilteredSelected ? 'check-square' : 'square'} />
                Select all
              </button>
              <div className="view-toggle" role="group" aria-label="View">
                <button type="button" className={view === 'grid' ? 'active' : ''} onClick={() => setView('grid')} aria-label="Grid view"><NwIcon name="dashboard" /></button>
                <button type="button" className={view === 'list' ? 'active' : ''} onClick={() => setView('list')} aria-label="List view"><NwIcon name="list" /></button>
              </div>
            </div>
          </div>

          {actionError && (
            <div className="card card-pad jobs-alert" role="alert">
              <p className="muted" style={{ color: 'var(--danger)' }}>{actionError}</p>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setActionError('')}>
                Dismiss
              </button>
            </div>
          )}

          {selectedIds.length > 0 && (
            <div className="jobs-bulkbar" role="status">
              <span className="bulk-count">
                <NwIcon name="check-circle" /> {selectedIds.length} selected
              </span>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={handleBulkDelete}
                disabled={busy}
              >
                <NwIcon name="trash" /> Delete selected
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedIds([])} disabled={busy}>
                Clear selection
              </button>
            </div>
          )}

          {visible.length === 0 ? (
            <div className="card card-pad" style={{ textAlign: 'center', padding: 48 }}>
              <h2 className="card-title">No jobs match your filters</h2>
              <p className="muted" style={{ marginTop: 6 }}>Try a different search or clear the status filter.</p>
              <button type="button" className="btn btn-secondary" style={{ marginTop: 16 }} onClick={() => resetToFirst(() => { setQuery(''); setFilter('All') })}>
                Clear filters
              </button>
            </div>
          ) : (
            <div className={view === 'grid' ? 'jobs-grid' : 'jobs-list'}>
              {visible.map((job, index) => (
                <Link
                  key={job.id}
                  to={`/jobs/${job.id}`}
                  className={`card job-card${selectedIds.includes(job.id) ? ' selected' : ''}`}
                >
                  <div className="job-card-top">
                    <span className={`tile tile-${TILE_TONES[index % TILE_TONES.length]}`}><NwIcon name="briefcase" /></span>
                    <span className={`chip ${job.status === 'open' ? 'chip-green' : 'chip-gray'}`}><span className="dot" /> {job.status === 'open' ? 'Open' : 'Closed'}</span>
                    <span className="job-card-actions">
                      <button
                        type="button"
                        className={`icon-btn${selectedIds.includes(job.id) ? ' icon-btn-active' : ''}`}
                        role="checkbox"
                        aria-checked={selectedIds.includes(job.id)}
                        aria-label={`Select "${job.title}"`}
                        disabled={busy}
                        onClick={(event) => {
                          event.preventDefault()
                          event.stopPropagation()
                          toggleSelected(job.id)
                        }}
                      >
                        <NwIcon name={selectedIds.includes(job.id) ? 'check' : 'square'} />
                      </button>
                      <button
                        type="button"
                        className="icon-btn icon-btn-danger"
                        aria-label={`Delete "${job.title}"`}
                        disabled={busy}
                        onClick={(event) => {
                          event.preventDefault()
                          event.stopPropagation()
                          handleDelete(job)
                        }}
                      >
                        <NwIcon name="trash" />
                      </button>
                    </span>
                  </div>
                  <h2 className="job-title">{job.title}</h2>
                  <p className="job-meta muted">
                    <NwIcon name="pin" /> {job.location || 'Location open'}
                    {job.company ? ` · ${job.company}` : ''}
                    {typeof job.experience_required === 'number' ? ` · ${job.experience_required} yrs` : ''}
                  </p>
                  <div className="skill-row">
                    {(job.required_skills || []).slice(0, 4).map((skill) => (
                      <span key={skill} className="chip">{skill}</span>
                    ))}
                    {(job.required_skills || []).length > 4 && (
                      <span className="chip chip-gray">+{(job.required_skills || []).length - 4}</span>
                    )}
                    {(job.required_skills || []).length === 0 && <span className="muted no-matches">No skills parsed yet</span>}
                  </div>
                  <div className="job-card-foot">
                    <strong>Posted {postedLabel(job.created_at)}</strong>
                    {(job.required_skills || []).length > 0 && (
                      <span className="chip chip-indigo"><NwIcon name="sparkle" /> {(job.required_skills || []).length} skills</span>
                    )}
                  </div>
                </Link>
              ))}
            </div>
          )}

          <footer className="jobs-foot">
            <span className="muted">
              Showing {visible.length} of {filtered.length} jobs
            </span>
            <div className="pager">
              <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={safePage === 1} aria-label="Previous page">
                <NwIcon name="chevron-left" />
              </button>
              {Array.from({ length: pageCount }, (_, i) => i + 1).map((n) => (
                <button key={n} type="button" className={n === safePage ? 'active' : ''} onClick={() => setPage(n)} aria-current={n === safePage ? 'page' : undefined}>
                  {n}
                </button>
              ))}
              <button type="button" onClick={() => setPage((p) => Math.min(pageCount, p + 1))} disabled={safePage === pageCount} aria-label="Next page">
                <NwIcon name="chevron-right" />
              </button>
            </div>
          </footer>
        </>
      )}
    </div>
  )
}
