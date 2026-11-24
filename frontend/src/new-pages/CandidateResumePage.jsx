import { useEffect, useRef, useState } from 'react'
import NwIcon from './NwIcon'
import {
  getResume,
  onboardCandidate,
  removeResume,
  updateCandidateProfile,
  uploadResume,
} from '../services/candidatePortal'
import { getCurrentUser } from '../services/auth'

const MAX_RESUME_BYTES = 5 * 1024 * 1024
const ALLOWED_EXTENSIONS = ['.pdf', '.docx']
const ACCEPT = '.pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document'

const STATUS_LABELS = {
  uploaded: 'Uploaded',
  text_only: 'Text on file',
  missing: 'Not uploaded',
}

function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return String(value)
  return date.toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' })
}

function formatBytes(bytes) {
  if (!bytes) return '0 KB'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function validateFile(file) {
  const name = (file.name || '').toLowerCase()
  const extension = name.slice(name.lastIndexOf('.'))
  if (!ALLOWED_EXTENSIONS.includes(extension)) {
    return 'Please upload a PDF or DOCX file.'
  }
  if (!file.size) {
    return 'That file is empty. Please upload a readable resume.'
  }
  if (file.size > MAX_RESUME_BYTES) {
    return 'Your resume must be 5 MB or smaller.'
  }
  return ''
}

export default function CandidateResumePage() {
  const [resume, setResume] = useState(null)
  const [text, setText] = useState('')
  const [selected, setSelected] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [savingText, setSavingText] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const fileInputRef = useRef(null)

  function applyState(state) {
    setResume(state)
    setText(state?.resume_text || '')
  }

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      try {
        let data = await getResume()
        if (!active) return
        applyState(data)
      } catch (e) {
        // If email confirmation interrupted onboarding, finish it once and
        // reload. Otherwise surface the original error.
        try {
          const user = await getCurrentUser()
          const meta = user?.user_metadata || {}
          const fullName = meta.full_name || meta.name
          if (fullName) {
            await onboardCandidate({ full_name: fullName, email: user?.email })
            const data = await getResume()
            if (active) applyState(data)
            return
          }
        } catch {
          // fall through to the original error
        }
        if (active) setError(e.message || 'Could not load your resume.')
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    return () => {
      active = false
    }
  }, [])

  function openPicker() {
    if (!uploading) fileInputRef.current?.click()
  }

  function resetInput() {
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  function chooseFile(file) {
    if (!file) return
    setError('')
    setNotice('')
    const problem = validateFile(file)
    if (problem) {
      setSelected(null)
      resetInput()
      setError(problem)
      return
    }
    setSelected(file)
  }

  function handleInputChange(event) {
    chooseFile(event.target.files?.[0])
  }

  function handleDragOver(event) {
    event.preventDefault()
    if (!uploading) setDragging(true)
  }

  function handleDragLeave(event) {
    event.preventDefault()
    if (event.currentTarget.contains(event.relatedTarget)) return
    setDragging(false)
  }

  function handleDrop(event) {
    event.preventDefault()
    setDragging(false)
    if (uploading) return
    chooseFile(event.dataTransfer?.files?.[0])
  }

  function clearSelection() {
    setSelected(null)
    resetInput()
  }

  async function handleUpload() {
    if (!selected || uploading) return
    setUploading(true)
    setError('')
    setNotice('')
    try {
      const state = await uploadResume(selected)
      applyState(state)
      setSelected(null)
      resetInput()
      setNotice('Resume uploaded and parsed.')
    } catch (e) {
      setError(e.message || 'Could not upload your resume.')
    } finally {
      setUploading(false)
    }
  }

  async function handleRemove() {
    if (removing) return
    if (!window.confirm('Remove your resume? Recruiters will no longer see it.')) return
    setRemoving(true)
    setError('')
    setNotice('')
    try {
      const state = await removeResume()
      applyState(state)
      setSelected(null)
      resetInput()
      setNotice('Resume removed.')
    } catch (e) {
      setError(e.message || 'Could not remove your resume.')
    } finally {
      setRemoving(false)
    }
  }

  async function handleSaveText() {
    if (savingText) return
    setSavingText(true)
    setError('')
    setNotice('')
    try {
      await updateCandidateProfile({ resume_text: text })
      const state = await getResume()
      applyState(state)
      setNotice('Pasted resume saved.')
    } catch (e) {
      setError(e.message || 'Could not save your resume text.')
    } finally {
      setSavingText(false)
    }
  }

  const hasResume = Boolean(resume?.has_resume)
  const statusLabel = STATUS_LABELS[resume?.status] || STATUS_LABELS.missing

  return (
    <div className="page np" style={{ padding: 24 }}>
      <header className="page-header">
        <div>
          <div className="eyebrow">Candidate portal</div>
          <h1 className="page-title">My Resume</h1>
          <p className="page-sub">
            Upload your resume to help recruiters understand your skills and experience.
          </p>
        </div>
      </header>

      {error && (
        <section className="card card-pad" role="alert" style={{ marginBottom: 18 }}>
          <p style={{ color: 'var(--danger)', margin: 0 }}>{error}</p>
        </section>
      )}
      {notice && (
        <section className="card card-pad" role="status" style={{ marginBottom: 18 }}>
          <p style={{ color: 'var(--success)', margin: 0 }}>{notice}</p>
        </section>
      )}

      {loading ? (
        <p className="muted">Loading your resume…</p>
      ) : (
        <div className="resume-grid">
          <div style={{ display: 'grid', gap: 18 }}>
            <section className="card card-pad" aria-label="Upload resume">
              <div className="card-head">
                <div>
                  <div className="eyebrow">Upload</div>
                  <h2 className="card-title">Add your resume file</h2>
                </div>
              </div>

              <div
                className={`resume-dropzone${dragging ? ' is-dragging' : ''}`}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <span className="resume-drop-icon"><NwIcon name="upload" /></span>
                <p className="resume-drop-title">Drag and drop your resume here</p>
                <p className="muted" style={{ margin: 0 }}>
                  Supported formats: PDF and DOCX · Maximum file size: 5 MB
                </p>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={openPicker}
                  disabled={uploading}
                >
                  <NwIcon name="file" /> Browse Files
                </button>
                <input
                  ref={fileInputRef}
                  id="candidate-resume-file"
                  type="file"
                  accept={ACCEPT}
                  aria-label="Resume file"
                  className="sr-only"
                  onChange={handleInputChange}
                  disabled={uploading}
                />
              </div>

              {selected && (
                <div className="resume-selected" style={{ marginTop: 14 }}>
                  <NwIcon name="file" />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="resume-file-name">{selected.name}</div>
                    <div className="resume-hint">{formatBytes(selected.size)}</div>
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={clearSelection}
                    disabled={uploading}
                  >
                    Clear
                  </button>
                </div>
              )}

              <div className="resume-actions">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleUpload}
                  disabled={uploading || !selected}
                >
                  <NwIcon name="upload" /> {uploading ? 'Uploading…' : 'Upload and Save'}
                </button>
              </div>
            </section>

            <section className="card card-pad" aria-label="Current resume">
              <div className="card-head">
                <div>
                  <div className="eyebrow">Current file</div>
                  <h2 className="card-title">Your resume</h2>
                </div>
                <span className={`chip ${hasResume ? 'chip-green' : 'chip-amber'}`}>
                  <span className="dot" /> {statusLabel}
                </span>
              </div>

              {resume?.file ? (
                <>
                  <div className="resume-file-row">
                    <span className="tile tile-indigo" aria-hidden="true"><NwIcon name="file" /></span>
                    <div style={{ minWidth: 0 }}>
                      <div className="resume-file-name">{resume.file.filename}</div>
                      <div className="resume-hint">
                        Uploaded {formatDate(resume.file.created_at)} · {formatBytes(resume.file.byte_size)}
                      </div>
                    </div>
                  </div>
                  <div className="resume-actions">
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={openPicker}
                      disabled={uploading || removing}
                    >
                      <NwIcon name="refresh" /> Replace
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger"
                      onClick={handleRemove}
                      disabled={removing || uploading}
                    >
                      <NwIcon name="trash" /> {removing ? 'Removing…' : 'Remove'}
                    </button>
                  </div>
                </>
              ) : (
                <p className="muted" style={{ margin: 0 }}>
                  {resume?.status === 'text_only'
                    ? 'You have pasted resume text on file. Upload a PDF or DOCX to replace it with a file.'
                    : 'No resume uploaded yet. Upload a PDF or DOCX so recruiters can review it.'}
                </p>
              )}
            </section>
          </div>

          <section className="card card-pad" aria-label="Paste resume text">
            <div className="card-head">
              <div>
                <div className="eyebrow">Alternative</div>
                <h2 className="card-title">Paste resume text</h2>
              </div>
            </div>
            <p className="muted">
              Prefer to type or paste instead? Your text is saved to your profile and used the
              same way a file is.
            </p>
            {resume?.file && (
              <p className="resume-hint" style={{ marginTop: 0 }}>
                A file is currently attached and its text takes precedence. Remove the file if
                you want your pasted text to be used.
              </p>
            )}
            <textarea
              className="textarea"
              style={{ width: '100%', minHeight: 220, marginTop: 12 }}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder="Paste your resume text here"
            />
            <div className="resume-actions">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleSaveText}
                disabled={savingText}
              >
                <NwIcon name="file" /> {savingText ? 'Saving…' : 'Save pasted resume'}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
