import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import NwIcon from './NwIcon'
import { deleteDocument, listDocuments, uploadDocument } from '../services/rag'
import { listCandidates } from '../services/candidates'
import { ApiError } from '../services/api'

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024

const SOURCE_TYPES = [
  { value: 'resume', label: 'Resume' },
  { value: 'job_description', label: 'Job description' },
  { value: 'knowledge', label: 'Knowledge base' },
]

const SOURCE_LABELS = SOURCE_TYPES.reduce((map, item) => {
  map[item.value] = item.label
  return map
}, {})

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'
  if (bytes < 1024) return `${bytes} B`
  const kilobytes = bytes / 1024
  if (kilobytes < 1024) {
    return `${kilobytes < 10 ? kilobytes.toFixed(1) : Math.round(kilobytes)} KB`
  }
  const megabytes = kilobytes / 1024
  return `${megabytes < 10 ? megabytes.toFixed(1) : Math.round(megabytes)} MB`
}

function extensionOf(name) {
  const index = name.lastIndexOf('.')
  return index === -1 ? '' : name.slice(index).toLowerCase()
}

function validateFile(file) {
  if (!file) return 'Choose a file to upload.'
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
    return `Unsupported file type. Use ${ACCEPTED_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return 'That file is empty.'
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)} per file.`
  }
  return ''
}

function formatDate(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Unknown date'
  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

export default function DocumentsPage() {
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)
  const [sourceType, setSourceType] = useState('resume')
  const [selectedFile, setSelectedFile] = useState(null)
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(null)
  const [uploadError, setUploadError] = useState('')
  const [success, setSuccess] = useState('')
  const [deletingId, setDeletingId] = useState('')
  const [toast, setToast] = useState('')
  const [candidates, setCandidates] = useState([])
  const [candidateId, setCandidateId] = useState('')
  const inputRef = useRef(null)

  useEffect(() => {
    let cancelled = false
    listCandidates()
      .then((data) => {
        if (cancelled) return
        setCandidates(Array.isArray(data) ? data : [])
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    listDocuments()
      .then((data) => {
        if (cancelled) return
        setDocuments(Array.isArray(data?.documents) ? data.documents : [])
        setLoadError('')
      })
      .catch((err) => {
        if (cancelled) return
        setLoadError(err instanceof ApiError ? err.message : 'Could not load your documents.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [reloadKey])

  useEffect(() => {
    if (!uploading || uploading.done) return undefined
    const timer = window.setTimeout(() => {
      setUploading((current) => (
        current && !current.done
          ? { ...current, progress: Math.min(90, current.progress + 8) }
          : current
      ))
    }, 320)
    return () => window.clearTimeout(timer)
  }, [uploading])

  useEffect(() => {
    if (!success) return undefined
    const timer = window.setTimeout(() => setSuccess(''), 7000)
    return () => window.clearTimeout(timer)
  }, [success])

  useEffect(() => {
    if (!toast) return undefined
    const timer = window.setTimeout(() => setToast(''), 2600)
    return () => window.clearTimeout(timer)
  }, [toast])

  function openPicker() {
    if (uploading) return
    inputRef.current?.click()
  }

  function pickFile(file) {
    if (!file || uploading) return
    setSelectedFile(file)
    setUploadError(validateFile(file))
    setSuccess('')
  }

  function onInputChange(event) {
    pickFile(event.target.files?.[0])
    event.target.value = ''
  }

  function onDragOver(event) {
    event.preventDefault()
    if (!uploading) setDragging(true)
  }

  function onDragLeave(event) {
    event.preventDefault()
    setDragging(false)
  }

  function onDrop(event) {
    event.preventDefault()
    setDragging(false)
    pickFile(event.dataTransfer.files?.[0])
  }

  async function handleUpload() {
    if (!selectedFile || uploading) return
    const problem = validateFile(selectedFile)
    if (problem) {
      setUploadError(problem)
      return
    }
    setUploadError('')
    setSuccess('')
    setUploading({
      name: selectedFile.name,
      size: selectedFile.size,
      progress: 8,
      done: false,
    })
    try {
      const created = await uploadDocument(
        selectedFile,
        sourceType,
        sourceType === 'resume' ? candidateId : '',
      )
      setDocuments((current) => [
        created,
        ...current.filter((item) => item.document_id !== created.document_id),
      ])
      setUploading((current) => (current ? { ...current, progress: 100, done: true } : current))
      setSelectedFile(null)
      setSuccess(
        `${created.filename} was uploaded and indexed into ${created.chunk_count} searchable ${created.chunk_count === 1 ? 'chunk' : 'chunks'}.`,
      )
      setToast(`${SOURCE_LABELS[created.source_type] || 'Document'} indexed`)
      window.setTimeout(() => {
        setUploading((current) => (current && current.done ? null : current))
      }, 1400)
    } catch (err) {
      setUploading(null)
      setUploadError(err instanceof ApiError ? err.message : 'Upload failed. Please try again.')
    }
  }

  async function handleDelete(doc) {
    if (deletingId) return
    const confirmed = window.confirm(
      `Delete "${doc.filename}" from your workspace? This cannot be undone.`,
    )
    if (!confirmed) return
    setDeletingId(doc.document_id)
    try {
      await deleteDocument(doc.document_id)
      setDocuments((current) => current.filter((item) => item.document_id !== doc.document_id))
      setToast(`${doc.filename} deleted`)
    } catch (err) {
      setToast(err instanceof ApiError ? err.message : 'Could not delete that document.')
    } finally {
      setDeletingId('')
    }
  }

  const uploadingLabel = uploading
    ? uploading.done
      ? 'Indexed'
      : 'Uploading and indexing…'
    : ''

  const candidateById = candidates.reduce((map, candidate) => {
    map[candidate.id] = candidate.full_name
    return map
  }, {})

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="nw-crumbs">
            <Link to="/dashboard" className="link">Dashboard</Link>
            <NwIcon name="chevron-right" />
            <span>Upload resumes</span>
          </div>
          <h1 className="page-title">Upload Resumes</h1>
          <p className="page-sub">
            Add resumes to your talent pool. Mitra extracts the text, splits it into chunks and
            indexes it so matching and assistant answers can cite the source.
          </p>
        </div>
        <div className="page-actions">
          <Link to="/dashboard" className="btn btn-secondary">
            <NwIcon name="chevron-left" /> Back to dashboard
          </Link>
        </div>
      </header>

      <div className="doc-grid">
        <section className="card doc-card" aria-label="Upload a document">
          <div className="card-head">
            <div>
              <h2 className="card-title">Add a file</h2>
              <p className="muted">Drag a file here or browse from your computer.</p>
            </div>
          </div>

          <div
            className={`doc-drop ${dragging ? 'is-dragging' : ''}`}
            role="button"
            tabIndex={0}
            aria-label="Choose a file to upload"
            onClick={openPicker}
            onKeyDown={(event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                openPicker()
              }
            }}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            onDrop={onDrop}
          >
            <span className="doc-drop-icon">
              <NwIcon name="upload" />
            </span>
            <strong>Drop a resume here</strong>
            <span className="muted">
              {ACCEPTED_EXTENSIONS.join(', ')} · up to {formatBytes(MAX_UPLOAD_BYTES)} per file
            </span>
            <span className="doc-drop-actions">
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={(event) => {
                  event.stopPropagation()
                  openPicker()
                }}
                disabled={Boolean(uploading)}
              >
                Browse files
              </button>
            </span>
            <input
              ref={inputRef}
              type="file"
              accept={ACCEPTED_EXTENSIONS.join(',')}
              className="sr-only"
              onChange={onInputChange}
              tabIndex={-1}
            />
          </div>

          <div className="doc-source">
            <label className="field">
              <span className="muted">Document type</span>
              <select
                className="select"
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
                disabled={Boolean(uploading)}
              >
                {SOURCE_TYPES.map((item) => (
                  <option key={item.value} value={item.value}>{item.label}</option>
                ))}
              </select>
            </label>
            {sourceType === 'resume' && (
              <label className="field">
                <span className="muted">Link to candidate</span>
                <select
                  className="select"
                  value={candidateId}
                  onChange={(event) => setCandidateId(event.target.value)}
                  disabled={Boolean(uploading)}
                >
                  <option value="">Not linked (matching won't use it)</option>
                  {candidates.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.full_name}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleUpload}
              disabled={!selectedFile || Boolean(uploading)}
            >
              <NwIcon name="upload" />
              {uploading && !uploading.done ? 'Uploading…' : 'Upload'}
            </button>
          </div>

          {selectedFile && (
            <div className="doc-selected">
              <NwIcon name="file" />
              <span className="doc-selected-main">
                <strong title={selectedFile.name}>{selectedFile.name}</strong>
                <span className="muted">
                  {formatBytes(selectedFile.size)} · {SOURCE_LABELS[sourceType]}
                </span>
              </span>
              <button
                type="button"
                className="icon-btn doc-delete"
                aria-label={`Remove ${selectedFile.name}`}
                title="Remove file"
                onClick={() => {
                  setSelectedFile(null)
                  setUploadError('')
                }}
                disabled={Boolean(uploading)}
              >
                <NwIcon name="x" />
              </button>
            </div>
          )}

          {uploading && (
            <div className="doc-progress">
              <div className="doc-progress-top">
                <span>{uploadingLabel}</span>
                <span>{uploading.progress}%</span>
              </div>
              <div
                className="doc-progress-track"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={uploading.progress}
                aria-label="Upload progress"
              >
                <span style={{ width: `${uploading.progress}%` }} />
              </div>
            </div>
          )}

          {uploadError && (
            <div className="doc-alert doc-alert-danger" role="alert">
              <NwIcon name="x-circle" />
              <span>{uploadError}</span>
            </div>
          )}

          {success && (
            <div className="doc-alert doc-alert-success" role="status">
              <NwIcon name="check-circle" />
              <span>{success}</span>
            </div>
          )}
        </section>

        <aside className="card doc-card" aria-label="Upload guidelines">
          <div className="card-head">
            <h2 className="card-title">Before you upload</h2>
          </div>
          <div className="doc-tips">
            <div className="doc-tip">
              <NwIcon name="file" />
              <span>
                <strong>Supported files</strong>
                {ACCEPTED_EXTENSIONS.join(', ')}
              </span>
            </div>
            <div className="doc-tip">
              <NwIcon name="shield" />
              <span>
                <strong>Size limit</strong>
                {formatBytes(MAX_UPLOAD_BYTES)} per file
              </span>
            </div>
            <div className="doc-tip">
              <NwIcon name="sparkle" />
              <span>
                <strong>What happens next</strong>
                The file is parsed, chunked and embedded so matching and assistant answers can cite it.
              </span>
            </div>
          </div>
        </aside>
      </div>

      <section className="card doc-card" aria-label="Uploaded documents">
        <div className="card-head">
          <div>
            <h2 className="card-title">Uploaded documents</h2>
            <p className="muted">
              {loading ? 'Loading your library…' : `${documents.length} ${documents.length === 1 ? 'document' : 'documents'} in this workspace`}
            </p>
          </div>
          <button
            type="button"
            className="icon-btn"
            onClick={() => setReloadKey((key) => key + 1)}
            aria-label="Refresh documents"
            title="Refresh"
            disabled={loading}
          >
            <NwIcon name="refresh" />
          </button>
        </div>

        {loadError ? (
          <div className="doc-alert doc-alert-danger" role="alert">
            <NwIcon name="x-circle" />
            <span>{loadError}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setReloadKey((key) => key + 1)}
            >
              Try again
            </button>
          </div>
        ) : loading ? (
          <p className="muted">Loading documents…</p>
        ) : documents.length === 0 ? (
          <div className="doc-empty">
            <NwIcon name="file" />
            <strong>No documents yet</strong>
            <span className="muted">Upload a resume to start building your searchable talent pool.</span>
          </div>
        ) : (
          <ul className="doc-list">
            {documents.map((doc) => (
              <li key={doc.document_id} className="doc-row">
                <span className="doc-file-icon">
                  <NwIcon name="file" />
                </span>
                <span className="doc-file-main">
                  <strong title={doc.filename}>{doc.filename}</strong>
                  <span className="muted">
                    {doc.chunk_count} {doc.chunk_count === 1 ? 'chunk' : 'chunks'} ·{' '}
                    {formatBytes(doc.byte_size)} · {formatDate(doc.created_at)}
                    {doc.candidate_id && candidateById[doc.candidate_id]
                      ? ` · linked: ${candidateById[doc.candidate_id]}`
                      : ''}
                  </span>
                </span>
                <span className={`chip ${doc.source_type === 'resume' ? 'chip-indigo' : 'chip-gray'}`}>
                  {SOURCE_LABELS[doc.source_type] || doc.source_type}
                </span>
                <button
                  type="button"
                  className="icon-btn doc-delete"
                  onClick={() => handleDelete(doc)}
                  disabled={Boolean(deletingId)}
                  aria-label={`Delete ${doc.filename}`}
                  title="Delete document"
                >
                  <NwIcon name={deletingId === doc.document_id ? 'refresh' : 'trash'} />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {toast && (
        <div className="toast" role="status">
          <NwIcon name="check-circle" />
          {toast}
        </div>
      )}
    </div>
  )
}
