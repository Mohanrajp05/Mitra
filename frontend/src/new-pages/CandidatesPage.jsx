import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import { listCandidates, deleteCandidate } from '../services/candidates'
import { ApiError } from '../services/api'

const experienceBands = [
  { key: 'any', label: 'Any exp.', test: () => true },
  { key: 'junior', label: '0–2 yrs', test: (y) => y < 2.5 },
  { key: 'mid', label: '3–5 yrs', test: (y) => y >= 2.5 && y <= 5.5 },
  { key: 'senior', label: '6+ yrs', test: (y) => y > 5.5 },
]

const MAX_SKILLS = 4

function toViewModel(row) {
  const created = row.created_at ? new Date(row.created_at).getTime() : 0
  return {
    id: row.id,
    name: row.full_name,
    email: row.email || '',
    contact: row.email || row.phone || '',
    skills: row.skills || [],
    education: row.education || '',
    years: typeof row.experience_years === 'number' ? row.experience_years : 0,
    created,
    source: null,
    bestFit: null,
  }
}

export default function CandidatesPage() {
  const navigate = useNavigate()
  const [list, setList] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [band, setBand] = useState('any')
  const [skills, setSkills] = useState([])
  const [sort, setSort] = useState('recent')
  const [toast, setToast] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const rows = await listCandidates()
        if (cancelled) return
        setList(rows.map(toViewModel))
        setError('')
      } catch (err) {
        if (cancelled) return
        setError(err instanceof ApiError ? err.message : 'Could not load candidates.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const skillFilters = useMemo(() => {
    const counts = new Map()
    list.forEach((c) => (c.skills || []).forEach((s) => {
      const key = s.trim()
      if (key) counts.set(key, (counts.get(key) || 0) + 1)
    }))
    return [...counts.entries()]
      .filter(([, count]) => count > 1)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([skill]) => skill)
  }, [list])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    const bandDef = experienceBands.find((b) => b.key === band) || experienceBands[0]
    const rows = list.filter((c) => {
      const haystack = [c.name, c.education, c.email, ...(c.skills || [])].join(' ').toLowerCase()
      const matchesQuery = !q || haystack.includes(q)
      const matchesSkills = skills.every((s) => (c.skills || []).some((cs) => cs.toLowerCase() === s.toLowerCase()))
      return matchesQuery && bandDef.test(c.years) && matchesSkills
    })
    const sorters = {
      recent: (a, b) => b.created - a.created,
      exp: (a, b) => b.years - a.years,
      name: (a, b) => a.name.localeCompare(b.name),
    }
    return [...rows].sort(sorters[sort] || sorters.recent)
  }, [list, query, band, skills, sort])

  function toggleSkill(skill) {
    setSkills((current) => (current.includes(skill) ? current.filter((s) => s !== skill) : [...current, skill]))
  }

  function flash(message) {
    setToast(message)
    window.setTimeout(() => setToast(''), 2200)
  }

  async function removeCandidate(candidate) {
    setList((current) => current.filter((c) => c.id !== candidate.id))
    flash(`${candidate.name} removed from your talent pool`)
    try {
      await deleteCandidate(candidate.id)
    } catch {
      flash(`Could not delete ${candidate.name} on the server`)
    }
  }

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Talent pool</div>
          <h1 className="page-title">Candidates</h1>
          <p className="page-sub">Everyone in your pipeline, ready for the next screen.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={() => {
            const firstCandidate = list[0]
            if (firstCandidate) navigate(`/candidates/${firstCandidate.id}`)
            else flash('Add a candidate, then upload their resume from the candidate profile')
          }}>
            <NwIcon name="upload" /> Manage resumes
          </button>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/candidates/new')}>
            <NwIcon name="user-plus" /> Add candidate
          </button>
        </div>
      </header>

      <section className="card cd-filters" aria-label="Candidate filters">
        <div className="cd-filter-row">
          <div className="input-wrap cd-search">
            <NwIcon name="search" />
            <input
              className="input"
              type="search"
              placeholder="Search by name, email, education or skill…"
              aria-label="Search candidates"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </div>
          <div className="cd-bands" role="group" aria-label="Years of experience">
            {experienceBands.map((b) => (
              <button key={b.key} type="button" className={band === b.key ? 'active' : ''} aria-pressed={band === b.key} onClick={() => setBand(b.key)}>
                {b.label}
              </button>
            ))}
          </div>
          <label className="cd-sort">
            <NwIcon name="filter" />
            <span className="sr-only">Sort by</span>
            <select className="select" value={sort} onChange={(e) => setSort(e.target.value)}>
              <option value="recent">Newest first</option>
              <option value="exp">Most experience</option>
              <option value="name">Name A–Z</option>
            </select>
          </label>
        </div>
        {skillFilters.length > 0 && (
          <div className="cd-skill-row">
            <span className="eyebrow">Skills</span>
            {skillFilters.map((s) => (
              <button key={s} type="button" className={`cd-skill-chip ${skills.includes(s) ? 'active' : ''}`} aria-pressed={skills.includes(s)} onClick={() => toggleSkill(s)}>
                {s}
              </button>
            ))}
            {skills.length > 0 && (
              <button type="button" className="link" onClick={() => setSkills([])}>Clear</button>
            )}
          </div>
        )}
      </section>

      <div className="cd-count-row">
        <strong>{loading ? 'Loading candidates…' : `${filtered.length} candidate${filtered.length === 1 ? '' : 's'}`}</strong>
        <span className="muted"><NwIcon name="sparkle" /> Match scores are computed on the Matches page</span>
      </div>

      {error && (
        <div className="card cd-error">
          <NwIcon name="x-circle" />
          <h2>Could not load candidates</h2>
          <p className="muted">{error}</p>
          <button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Try again</button>
        </div>
      )}

      {!error && loading && list.length === 0 && (
        <div className="card cd-loading"><span className="spinner" aria-hidden="true" /> Fetching your talent pool…</div>
      )}

      {!error && !loading && filtered.length === 0 && (
        <div className="card cd-empty">
          <NwIcon name="users" />
          <h2>{list.length === 0 ? 'No candidates yet' : 'No candidates match these filters'}</h2>
          <p className="muted">
            {list.length === 0
              ? 'Add a candidate, then upload their resume from the candidate profile.'
              : 'Try removing a skill or widening the experience range.'}
          </p>
          {list.length === 0 ? (
            <button type="button" className="btn btn-primary" onClick={() => navigate('/assistant')}>
              <NwIcon name="upload" /> Go to assistant
            </button>
          ) : (
            <button type="button" className="btn btn-secondary" onClick={() => { setQuery(''); setBand('any'); setSkills([]) }}>Reset filters</button>
          )}
        </div>
      )}

      {!error && filtered.length > 0 && (
        <div className="cd-grid">
          {filtered.map((c) => (
            <article key={c.id} className="card cd-card">
              <div className="cd-top">
                <Avatar name={c.name} size={44} />
                <div className="cd-id">
                  <h2>{c.name}</h2>
                  <p className="muted">{c.education || 'Candidate profile'}</p>
                  {c.contact && <p className="muted cd-loc"><NwIcon name="mail" /> {c.contact}</p>}
                </div>
                {c.source && <span className="chip chip-gray">{c.source}</span>}
              </div>

              {c.skills.length > 0 && (
                <div className="cd-skills">
                  {c.skills.slice(0, MAX_SKILLS).map((s) => (
                    <span key={s} className="chip chip-indigo">{s}</span>
                  ))}
                  {c.skills.length > MAX_SKILLS && <span className="chip chip-gray">+{c.skills.length - MAX_SKILLS}</span>}
                </div>
              )}

              <dl className="cd-facts">
                <div>
                  <dt>Experience</dt>
                  <dd>{c.years} years</dd>
                </div>
                <div>
                  <dt>Education</dt>
                  <dd>{c.education || '—'}</dd>
                </div>
              </dl>

              <div className="cd-actions">
                <Link to={`/candidates/${c.id}`} className="btn btn-primary btn-sm cd-view">View details</Link>
                <button type="button" className="icon-btn" aria-label={`Message ${c.name}`} onClick={() => navigate('/messages')}>
                  <NwIcon name="mail" />
                </button>
                <button type="button" className="icon-btn" aria-label={`Remove ${c.name}`} onClick={() => removeCandidate(c)}>
                  <NwIcon name="trash" />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <NwIcon name="check" /> {toast}
        </div>
      )}
    </div>
  )
}
