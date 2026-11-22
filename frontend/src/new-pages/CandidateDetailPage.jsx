import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import ScoreRing from './ScoreRing'
import { getCandidate, getConsent, updateConsent } from '../services/candidates'
import { listJobs } from '../services/jobs'
import { deleteDocument, uploadDocument, matchCandidate, fetchDocumentFile } from '../services/rag'
import { ApiError } from '../services/api'

const parseSteps = ['Reading file', 'Extracting text', 'Splitting into chunks', 'Generating embeddings', 'Indexed for search']

function useToast() {
  const [toast, setToast] = useState('')
  const flash = (message) => {
    setToast(message)
    window.setTimeout(() => setToast(''), 2400)
  }
  return [toast, flash]
}

export default function CandidateDetailPage() {
  const { candidateId } = useParams()
  const navigate = useNavigate()
  const [toast, flash] = useToast()

  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [candidate, setCandidate] = useState(null)
  const [documents, setDocuments] = useState([])
  const [fits, setFits] = useState([])

  const [upload, setUpload] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [notes, setNotes] = useState([])
  const [draftNote, setDraftNote] = useState('')
  const [consent, setConsent] = useState(null)
  const [consentBusy, setConsentBusy] = useState(false)
  const [deletingDocumentId, setDeletingDocumentId] = useState('')
  const [busyDocumentId, setBusyDocumentId] = useState('')
  const fileInput = useRef(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setLoadError('')
      try {
        const row = await getCandidate(candidateId)
        if (cancelled) return
        setCandidate(row)
        setNotes([])
        try {
          const record = await getConsent(candidateId, 'resume_processing')
          if (!cancelled) setConsent(record || null)
        } catch {
          if (!cancelled) setConsent(null)
        }
        if (!cancelled) setDocuments((row.resume_documents || []))
        try {
          const jobs = await listJobs()
          if (!cancelled) {
            setFits(jobs.slice(0, 4).map((job) => ({ job, score: null, relevance: null, explanation: '', loading: false })))
          }
        } catch {
          if (!cancelled) setFits([])
        }
      } catch (err) {
        if (!cancelled) {
          setLoadError(err instanceof ApiError ? err.message : 'Could not load this candidate.')
          setCandidate(null)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [candidateId])

  const resumes = useMemo(
    () => documents.filter((d) => d.source_type !== 'job_description'),
    [documents],
  )

  async function runMatch(jobId) {
    setFits((current) => current.map((f) => (f.job.id === jobId ? { ...f, loading: true } : f)))
    try {
      const response = await matchCandidate(candidateId, jobId)
      setFits((current) => current.map((f) => (
        f.job.id === jobId
          ? {
            ...f,
            score: Math.round(response.match.relevance_score * 100),
            relevance: response.match.relevance,
            explanation: response.match.explanation,
            loading: false,
          }
          : f
      )))
    } catch (err) {
      setFits((current) => current.map((f) => (f.job.id === jobId ? { ...f, loading: false } : f)))
      flash(err instanceof ApiError ? err.message : 'Match check failed.')
    }
  }

  const firstPendingFit = useMemo(() => fits.find((f) => f.score === null && !f.loading), [fits])

  useEffect(() => {
    if (!loading && candidate && firstPendingFit) runMatch(firstPendingFit.job.id)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, candidateId])

  async function ensureConsent() {
    let status = consent ? consent.status : null
    if (!status) {
      try {
        const record = await getConsent(candidateId, 'resume_processing')
        setConsent(record || null)
        status = record ? record.status : null
      } catch {
        status = null
      }
    }
    if (status === 'granted') return true
    const proceed = window.confirm('Resume processing consent has not been granted for this candidate. Grant consent and upload?')
    if (!proceed) return false
    setConsentBusy(true)
    try {
      await updateConsent(candidateId, 'resume_processing', true)
      setConsent({ ...(consent || {}), status: 'granted' })
      flash('Consent granted for resume processing')
      return true
    } catch (err) {
      flash(err instanceof ApiError ? err.message : 'Could not save consent.')
      return false
    } finally {
      setConsentBusy(false)
    }
  }

  async function toggleConsent() {
    const granting = !(consent && consent.status === 'granted')
    if (!granting && !window.confirm('Withdraw resume processing consent for this candidate?')) return
    setConsentBusy(true)
    try {
      await updateConsent(candidateId, 'resume_processing', granting)
      setConsent({ ...(consent || {}), status: granting ? 'granted' : 'withdrawn' })
      flash(granting ? 'Consent granted for resume processing' : 'Consent withdrawn')
    } catch (err) {
      flash(err instanceof ApiError ? err.message : 'Could not save consent.')
    } finally {
      setConsentBusy(false)
    }
  }

  useEffect(() => {
    if (!upload || upload.done) return undefined
    const timer = window.setTimeout(() => {
      setUpload((u) => (u && !u.done ? { ...u, progress: Math.min(90, u.progress + 9) } : u))
    }, 320)
    return () => window.clearTimeout(timer)
  }, [upload])

  function toResumeSummary(document) {
    return {
      document_id: document.document_id,
      filename: document.filename,
      mime_type: document.mime_type || '',
      byte_size: document.byte_size || 0,
      chunk_count: document.chunk_count || 0,
      created_at: document.created_at || '',
      source_type: document.source_type || 'resume',
    }
  }

  async function refreshCandidate() {
    try {
      const row = await getCandidate(candidateId)
      setCandidate(row)
      setDocuments(row.resume_documents || [])
    } catch {
      // Keep showing the current data if the refresh fails.
    }
  }

  async function startUpload(file) {
    if (!file) return
    const allowed = await ensureConsent()
    if (!allowed) return
    setUpload({ name: file.name, progress: 8, done: false })
    try {
      const document = await uploadDocument(file, 'resume', candidateId, null)
      setDocuments((current) => [
        toResumeSummary(document),
        ...current.filter((d) => d.document_id !== document.document_id),
      ])
      setUpload((u) => (u ? { ...u, progress: 100, done: true } : u))
      flash('Resume parsed and indexed')
      // Refresh so the resume text section reflects the newly linked file.
      refreshCandidate()
      window.setTimeout(() => setUpload(null), 1800)
    } catch (err) {
      setUpload(null)
      flash(err instanceof ApiError ? err.message : 'Resume upload failed.')
    }
  }

  async function removeResume(document) {
    if (deletingDocumentId) return
    if (!window.confirm(`Delete "${document.filename}" from this candidate? This cannot be undone.`)) return
    setDeletingDocumentId(document.document_id)
    try {
      await deleteDocument(document.document_id)
      setDocuments((current) => current.filter((d) => d.document_id !== document.document_id))
      flash('Resume removed from the candidate and RAG index')
      refreshCandidate()
    } catch (err) {
      flash(err instanceof ApiError ? err.message : 'Could not delete this resume.')
    } finally {
      setDeletingDocumentId('')
    }
  }

  function formatBytes(size) {
    if (!Number.isFinite(size) || size <= 0) return ''
    if (size < 1024) return `${size} B`
    if (size < 1024 * 1024) return `${Math.max(1, Math.round(size / 1024))} KB`
    return `${(size / (1024 * 1024)).toFixed(1)} MB`
  }

  function fileKindLabel(document) {
    const mime = (document.mime_type || '').toLowerCase()
    const name = (document.filename || '').toLowerCase()
    if (mime.includes('pdf') || name.endsWith('.pdf')) return 'PDF'
    if (mime.includes('word') || /\.(docx?|rtf)$/.test(name)) return 'DOCX'
    if (mime.includes('text') || /\.(txt|md)$/.test(name)) return 'TXT/MD'
    return 'File'
  }

  async function openResume(document, mode) {
    if (busyDocumentId) return
    setBusyDocumentId(document.document_id)
    try {
      const { blob } = await fetchDocumentFile(document.document_id)
      const url = URL.createObjectURL(blob)
      if (mode === 'view') {
        window.open(url, '_blank', 'noopener')
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      } else {
        const anchor = window.document.createElement('a')
        anchor.href = url
        anchor.download = document.filename || 'resume'
        anchor.click()
        window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      }
    } catch (err) {
      flash(err instanceof ApiError ? err.message : 'Could not retrieve the resume.')
    } finally {
      setBusyDocumentId('')
    }
  }

  function onDrop(event) {
    event.preventDefault()
    setDragging(false)
    startUpload(event.dataTransfer.files[0])
  }

  function addNote(event) {
    event.preventDefault()
    const text = draftNote.trim()
    if (!text) return
    setNotes((n) => [...n, { id: Date.now(), by: 'You', text }])
    setDraftNote('')
  }

  if (loading && !candidate) {
    return (
      <div className="page np">
        <div className="card cd-loading"><span className="spinner" aria-hidden="true" /> Loading candidate…</div>
      </div>
    )
  }

  if (loadError && !candidate) {
    return (
      <div className="page np">
        <div className="card card-pad cdd-missing">
          <h1 className="card-title">Candidate not found</h1>
          <p className="muted">{loadError}</p>
          <Link to="/candidates" className="btn btn-secondary">Back to candidates</Link>
        </div>
      </div>
    )
  }

  const name = candidate.full_name
  const years = typeof candidate.experience_years === 'number' ? candidate.experience_years : null
  const bestFit = fits.find((f) => f.score !== null)
  const parsing = upload && !upload.done
  const doneSteps = upload ? Math.floor((Math.min(upload.progress, 100) / 100) * parseSteps.length) : parseSteps.length
  const summaryParts = [
    `${name.split(' ')[0]} has ${years === null ? 'an unstated number of' : years} year${years === 1 ? '' : 's'} of experience. `,
  ]
  if (bestFit) {
    summaryParts.push(`Best fit right now: `)
    summaryParts.push({ bold: bestFit.job.title })
    summaryParts.push(` (${bestFit.score}% match).`)
  } else {
    summaryParts.push('Add a job to see how well this profile fits your open roles.')
  }

  const contactItems = [
    candidate.email ? { icon: 'mail', text: candidate.email } : null,
    candidate.phone ? { icon: 'phone', text: candidate.phone } : null,
  ].filter(Boolean)

  return (
    <div className="page np">
      <nav className="nw-crumbs" aria-label="Breadcrumb">
        <Link to="/candidates">Candidates</Link> <NwIcon name="chevron-right" /> <span>{name}</span>
      </nav>

      <header className="card cdd-head">
        <div className="cdd-banner" aria-hidden="true" />
        <div className="cdd-head-body">
          <Avatar name={name} size={84} />
          <div className="cdd-head-main">
            <h1>
              {name}
              <span className="chip chip-indigo">Candidate</span>
            </h1>
            <p className="muted">
              {years !== null ? `${years} years experience` : 'Experience not recorded'}
              {candidate.education ? ` · ${candidate.education}` : ''}
            </p>
            <p className="cdd-contact muted">
              {contactItems.map((item) => (
                <span key={item.icon}><NwIcon name={item.icon} /> {item.text}</span>
              ))}
            </p>
          </div>
          <div className="page-actions cdd-actions">
            <button type="button" className="btn btn-secondary" onClick={() => navigate('/messages')}>
              <NwIcon name="message" /> Message
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => navigate('/interviews')}>
              <NwIcon name="calendar" /> Schedule
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => flash('Interview scheduling works from the Interviews page')}
            >
              <NwIcon name="star" /> Move to interview
            </button>
          </div>
        </div>
      </header>

      <div className="cdd-layout">
        <div className="cdd-main">
          <section className="ai-card cdd-summary" aria-label="Mitra summary">
            <div className="ai-badge"><NwIcon name="sparkle" /> Mitra suggests · Summary</div>
            <p className="cdd-summary-text">
              {summaryParts.map((p, i) => (typeof p === 'string' ? <span key={i}>{p}</span> : <strong key={i}>{p.bold}</strong>))}
            </p>
            {bestFit && bestFit.explanation && (
              <p className="cdd-summary-text muted" style={{ marginTop: -6 }}>{bestFit.explanation}</p>
            )}
            <div className="cdd-tags">
              {years !== null && (
                <span className="chip chip-green">
                  <NwIcon name="chevron-up" /> {years} yrs experience
                </span>
              )}
              {(candidate.skills || []).length > 0 && (
                <span className="chip chip-indigo">{candidate.skills.length} skills parsed</span>
              )}
            </div>
          </section>

          <section className="card card-pad">
            <div className="card-head">
              <div>
                <div className="eyebrow">Parsed from resume</div>
                <h2 className="card-title">Skills</h2>
              </div>
              <button type="button" className="link cdd-edit" onClick={() => navigate('/assistant')}>
                <NwIcon name="edit" /> Ask Mitra to verify
              </button>
            </div>
            <div className="cdd-skill-groups">
              <div className="cdd-skill-group">
                <span className="muted">Skills</span>
                <div className="cdd-chips">
                  {(candidate.skills || []).length === 0
                    ? <span className="muted">No skills parsed yet. Upload a resume to fill this in.</span>
                    : candidate.skills.map((s) => <span key={s} className="chip chip-indigo">{s}</span>)}
                </div>
              </div>
            </div>
          </section>

          {candidate.extracted_profile && (
            <section className="card card-pad" aria-label="Extracted profile">
              <div className="card-head">
                <div>
                  <div className="eyebrow">Extracted from linked resume</div>
                  <h2 className="card-title">Candidate profile</h2>
                </div>
                <span
                  className={`chip ${candidate.extracted_profile.extraction_method === 'ollama_assisted' ? 'chip-amber' : 'chip-green'}`}
                  title={
                    candidate.extracted_profile.extraction_method === 'ollama_assisted'
                      ? 'Parsed deterministically, with evidence-verified AI help for unstructured sections'
                      : 'Parsed directly from the resume text — every value appears verbatim in the resume'
                  }
                >
                  <NwIcon name="sparkle" />
                  {candidate.extracted_profile.extraction_method === 'ollama_assisted' ? 'AI-assisted · verified' : 'Verified parse'}
                </span>
              </div>

              {candidate.extracted_profile.summary && (
                <p className="cdd-summary-text">{candidate.extracted_profile.summary}</p>
              )}

              {(candidate.extracted_profile.experience || []).length > 0 && (
                <div className="cdd-xp-block">
                  <span className="muted cdd-xp-label">Work experience</span>
                  <ul className="cdd-xp-list">
                    {candidate.extracted_profile.experience.map((entry, i) => (
                      <li key={`${entry.title || 'role'}-${entry.company || 'company'}-${i}`}>
                        <NwIcon name="briefcase" />
                        <div>
                          <strong>{[entry.title, entry.company].filter(Boolean).join(' · ')}</strong>
                          {entry.period && <span className="muted">{entry.period}</span>}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {(candidate.extracted_profile.education || []).length > 0 && (
                <div className="cdd-xp-block">
                  <span className="muted cdd-xp-label">Education</span>
                  {candidate.extracted_profile.education.map((item, i) => (
                    <div key={i} className="cdd-edu">
                      <span className="cdd-logo" aria-hidden="true"><NwIcon name="graduation" /></span>
                      <div><strong>{item}</strong></div>
                    </div>
                  ))}
                </div>
              )}

              {(candidate.extracted_profile.certifications || []).length > 0 && (
                <div className="cdd-xp-block">
                  <span className="muted cdd-xp-label">Certifications</span>
                  <div className="cdd-chips">
                    {candidate.extracted_profile.certifications.map((item, i) => (
                      <span key={i} className="chip chip-indigo">{item}</span>
                    ))}
                  </div>
                </div>
              )}

              {(candidate.extracted_profile.skills || []).length > 0 && (
                <div className="cdd-xp-block">
                  <span className="muted cdd-xp-label">Skills (extracted)</span>
                  <div className="cdd-chips">
                    {candidate.extracted_profile.skills.map((skill) => (
                      <span key={skill} className="chip chip-indigo">{skill}</span>
                    ))}
                  </div>
                </div>
              )}

              <div className="cdd-xp-meta">
                {typeof candidate.extracted_profile.total_years === 'number' && (
                  <span className="chip chip-green"><NwIcon name="chevron-up" /> {candidate.extracted_profile.total_years} yrs experience</span>
                )}
                {candidate.extracted_profile.contact?.email && (
                  <span className="chip chip-gray"><NwIcon name="mail" /> {candidate.extracted_profile.contact.email}</span>
                )}
                {candidate.extracted_profile.contact?.phone && (
                  <span className="chip chip-gray"><NwIcon name="phone" /> {candidate.extracted_profile.contact.phone}</span>
                )}
              </div>
            </section>
          )}

          <section className="card card-pad">
            <div className="eyebrow">Parsed from resume</div>
            <h2 className="card-title cdd-section-title">Education</h2>
            {candidate.education ? (
              <div className="cdd-edu">
                <span className="cdd-logo" aria-hidden="true"><NwIcon name="graduation" /></span>
                <div>
                  <strong>{candidate.education}</strong>
                </div>
              </div>
            ) : (
              <p className="muted">Education details haven’t been parsed for this candidate yet.</p>
            )}
          </section>

          <section className="card card-pad">
            <div className="eyebrow">Parsed from resume</div>
            <h2 className="card-title cdd-section-title">Resume text</h2>
            {candidate.resume_text ? (
              <p className="cdd-summary-text" style={{ whiteSpace: 'pre-line' }}>{candidate.resume_text}</p>
            ) : (
              <p className="muted">No resume text stored for this candidate yet.</p>
            )}
          </section>
        </div>

        <aside className="cdd-side">
          <section className="card card-pad">
            <div className="card-head">
              <div className="eyebrow">Consent</div>
              <span className={`chip ${consent && consent.status === 'granted' ? 'chip-green' : consent && consent.status === 'withdrawn' ? 'chip-amber' : 'chip-gray'}`}>
                <span className="dot" /> {consent ? (consent.status === 'granted' ? 'Granted' : consent.status === 'withdrawn' ? 'Withdrawn' : consent.status) : 'Not recorded'}
              </span>
            </div>
            <p className="muted" style={{ fontSize: 12.5 }}>
              Resume processing consent lets Mitra read and index this candidate’s resume.
            </p>
            <button
              type="button"
              className={`btn btn-sm ${consent && consent.status === 'granted' ? 'btn-secondary' : 'btn-primary'}`}
              disabled={consentBusy}
              onClick={toggleConsent}
            >
              <NwIcon name={consent && consent.status === 'granted' ? 'x' : 'check'} />
              {consent && consent.status === 'granted' ? 'Withdraw consent' : 'Grant consent'}
            </button>
          </section>

          <section className="card card-pad">
            <div className="card-head">
              <div className="eyebrow">Resume</div>
              <span className="muted cdd-file-meta">PDF, DOCX · 10 MB</span>
            </div>

            <div
              className={`cdd-drop ${dragging ? 'dragging' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={onDrop}
            >
              <NwIcon name="upload" />
              <strong>Drop a new resume here</strong>
              <span className="muted">
                or{' '}
                <button type="button" className="link" onClick={() => fileInput.current && fileInput.current.click()}>browse files</button>
                {' '}— Mitra will re-parse it
              </span>
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.doc,.docx,.txt,.md"
                className="sr-only"
                aria-label="Upload resume"
                onChange={(e) => startUpload(e.target.files[0])}
              />
            </div>

            {upload && (
              <div className="cdd-upload">
                <div className="cdd-file-row">
                  <NwIcon name="file" />
                  <div>
                    <strong>{upload.name}</strong>
                    <span className="muted">{parsing ? `Reading… ${upload.progress}%` : 'Parsed just now'}</span>
                  </div>
                </div>
                <div className="cdd-progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={upload.progress}>
                  <span style={{ width: `${upload.progress}%` }} />
                </div>
                <ul className="cdd-steps">
                  {parseSteps.map((step, i) => (
                    <li key={step} className={i < doneSteps ? 'done' : ''}>
                      <NwIcon name={i < doneSteps ? 'check-circle' : 'clock'} /> {step}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {resumes.length === 0 ? (
              <div className="cdd-file-row cdd-current">
                <NwIcon name="file" />
                <div>
                  <strong>No resume linked yet</strong>
                  <span className="muted">
                    Upload a resume above — it will be parsed, linked to this
                    candidate and used for matching.
                  </span>
                </div>
              </div>
            ) : (
              resumes.map((document) => (
                <div key={document.document_id} className="cdd-file-row cdd-current">
                  <NwIcon name="file" />
                  <div>
                    <strong>{document.filename}</strong>
                    <span className="muted">
                      {[
                        document.chunk_count > 0
                          ? `Parsed · ${document.chunk_count} chunks indexed`
                          : 'Processing…',
                        fileKindLabel(document),
                        formatBytes(document.byte_size),
                        document.created_at
                          ? new Date(document.created_at).toLocaleDateString()
                          : '',
                      ].filter(Boolean).join(' · ')}
                    </span>
                  </div>
                  <div className="cdd-file-actions">
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`View ${document.filename}`}
                      title="View resume"
                      disabled={busyDocumentId === document.document_id}
                      onClick={() => openResume(document, 'view')}
                    >
                      <NwIcon name="external" />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Download ${document.filename}`}
                      title="Download resume"
                      disabled={busyDocumentId === document.document_id}
                      onClick={() => openResume(document, 'download')}
                    >
                      <NwIcon name="download" />
                    </button>
                    <button
                      type="button"
                      className="icon-btn"
                      aria-label={`Delete ${document.filename}`}
                      title="Delete resume"
                      disabled={deletingDocumentId === document.document_id}
                      onClick={() => removeResume(document)}
                    >
                      <NwIcon name="trash" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </section>

          <section className="card card-pad">
            <div className="eyebrow">Matches</div>
            <h2 className="card-title cdd-section-title">Fit for open jobs</h2>
            {fits.length === 0 ? (
              <p className="muted">No open jobs yet. Create a job to see fit scores here.</p>
            ) : (
              <ul className="cdd-fits">
                {fits.map((f) => (
                  <li key={f.job.id}>
                    <div className="cdd-fit-row">
                      {f.score !== null ? <ScoreRing score={f.score} size={38} /> : (
                        <span className="tile-mini" aria-hidden="true"><NwIcon name={f.loading ? 'clock' : 'target'} /></span>
                      )}
                      <span>
                        <strong>{f.job.title}</strong>
                        <small className="muted">
                          {f.loading
                            ? 'Checking match…'
                            : f.score !== null
                              ? `${f.relevance} match · check details on Matches`
                              : f.job.required_skills && f.job.required_skills.length > 0
                                ? `${f.job.required_skills.length} required skills`
                                : 'No skill requirements listed'}
                        </small>
                      </span>
                      {f.score === null && !f.loading && (
                        <button type="button" className="link" onClick={() => runMatch(f.job.id)}>Check</button>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section className="card card-pad">
            <div className="eyebrow">Your notes</div>
            <ul className="cdd-notes">
              {notes.map((n) => (
                <li key={n.id}>
                  <Avatar name={n.by} size={24} />
                  <p>{n.text}</p>
                </li>
              ))}
              {notes.length === 0 && <li className="muted">No notes yet.</li>}
            </ul>
            <form onSubmit={addNote} className="cdd-note-form">
              <label className="sr-only" htmlFor="cdd-note">Add a note</label>
              <input id="cdd-note" className="input" placeholder="Add a note…" value={draftNote} onChange={(e) => setDraftNote(e.target.value)} />
              <button type="submit" className="btn btn-secondary btn-sm" disabled={!draftNote.trim()}>Add</button>
            </form>
          </section>
        </aside>
      </div>

      {toast && (
        <div className="toast" role="status">
          <NwIcon name="check" /> {toast}
        </div>
      )}
    </div>
  )
}
