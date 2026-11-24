import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import NwIcon from './NwIcon'
import { fetchDocumentFile } from '../services/rag'
import { getCandidateProfile, getResume, updateCandidateProfile } from '../services/candidatePortal'

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

function openDocumentWindow(blobUrl) {
  const link = document.createElement('a')
  link.href = blobUrl
  link.target = '_blank'
  link.rel = 'noopener'
  document.body.appendChild(link)
  link.click()
  link.remove()
}

function downloadDocumentBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 5_000)
}

export default function CandidateProfilePage() {
  const [profile, setProfile] = useState(null)
  const [resume, setResume] = useState(null)
  const [form, setForm] = useState({})
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  function formFromProfile(p) {
    return {
      full_name: p?.full_name || '',
      email: p?.email || '',
      phone: p?.phone || '',
      location: p?.location || '',
      skills: (p?.skills || []).join(', '),
      education: p?.education || '',
      experience_years: p?.experience_years ?? '',
    }
  }

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [profileData, resumeData] = await Promise.all([
          getCandidateProfile(),
          getResume().catch(() => null),
        ])
        if (!active) return
        setProfile(profileData)
        setResume(resumeData)
        setForm(formFromProfile(profileData))
      } catch (e) {
        if (active) setError(e.message)
      }
    }
    load()
    return () => {
      active = false
    }
  }, [])

  function startEdit() {
    setError('')
    setNotice('')
    setForm(formFromProfile(profile))
    setEditing(true)
  }

  function cancelEdit() {
    setForm(formFromProfile(profile))
    setEditing(false)
    setError('')
  }

  async function save() {
    setSaving(true)
    setError('')
    setNotice('')
    try {
      const payload = {
        full_name: form.full_name,
        phone: form.phone || null,
        location: form.location || null,
        skills: (form.skills || '')
          .split(',')
          .map((s) => s.trim())
          .filter(Boolean),
        education: form.education || null,
        experience_years: form.experience_years ? Number(form.experience_years) : null,
      }
      const updated = await updateCandidateProfile(payload)
      setProfile(updated)
      setResume((current) => (current ? { ...current, ...current } : current))
      setForm(formFromProfile(updated))
      setEditing(false)
      setNotice('Profile updated.')
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleViewResume() {
    if (!resume?.file?.document_id) return
    try {
      const { blob } = await fetchDocumentFile(resume.file.document_id)
      const url = URL.createObjectURL(blob)
      openDocumentWindow(url)
    } catch (e) {
      setError(e.message || 'Could not open your resume.')
    }
  }

  async function handleDownloadResume() {
    if (!resume?.file?.document_id) return
    try {
      const { blob, filename } = await fetchDocumentFile(resume.file.document_id)
      downloadDocumentBlob(blob, filename || resume.file.filename)
    } catch (e) {
      setError(e.message || 'Could not download your resume.')
    }
  }

  if (!profile) return <div style={{ padding: 24 }}>Loading…</div>

  const skills = Array.isArray(profile.skills) ? profile.skills : []
  const resumeStatus = resume?.status || (resume?.file ? 'uploaded' : 'missing')
  const resumeFilename = resume?.file?.filename || ''

  return (
    <div className="page np" style={{ padding: 24, maxWidth: 720 }}>
      <h1 className="page-title">My Profile</h1>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      {notice && <p style={{ color: 'var(--success)' }}>{notice}</p>}

      {!editing && (
        <>
          <div className="card card-pad" style={{ marginTop: 16 }}>
            <div className="card-head">
              <div>
                <div className="eyebrow">Profile</div>
                <h2 className="card-title">Your information</h2>
              </div>
              <button type="button" className="btn btn-primary" onClick={startEdit}>
                <NwIcon name="edit" /> Edit Profile
              </button>
            </div>

            <dl className="cd-facts" style={{ marginTop: 12 }}>
              <div><dt>Full name</dt><dd>{profile.full_name || '—'}</dd></div>
              <div><dt>Email</dt><dd>{profile.email || '—'}</dd></div>
              <div><dt>Phone</dt><dd>{profile.phone || '—'}</dd></div>
              <div><dt>Location</dt><dd>{profile.location || '—'}</dd></div>
              <div><dt>Education</dt><dd>{profile.education || '—'}</dd></div>
              <div><dt>Experience</dt><dd>{profile.experience_years != null ? `${profile.experience_years} years` : '—'}</dd></div>
            </dl>

            <div style={{ marginTop: 16 }}>
              <div className="eyebrow" style={{ marginBottom: 6 }}>Skills</div>
              {skills.length === 0 ? (
                <p className="muted" style={{ margin: 0 }}>No skills added yet.</p>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {skills.map((skill) => (
                    <span key={skill} className="chip chip-indigo">{skill}</span>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="card card-pad" style={{ marginTop: 18 }} aria-label="My Resume">
            <div className="card-head">
              <div>
                <div className="eyebrow">Resume</div>
                <h2 className="card-title">My Resume</h2>
              </div>
              <span className={`chip ${resume?.has_resume ? 'chip-green' : 'chip-amber'}`}>
                <span className="dot" /> {resumeStatus === 'missing' ? 'Not uploaded' : STATUS_LABELS[resumeStatus] || 'Uploaded'}
              </span>
            </div>

            {resume?.file ? (
              <>
                <div className="resume-file-row" style={{ marginTop: 12 }}>
                  <span className="tile tile-indigo" aria-hidden="true"><NwIcon name="file" /></span>
                  <div style={{ minWidth: 0 }}>
                    <div className="resume-file-name">{resumeFilename}</div>
                    <div className="resume-hint">
                      {String(resume.file.filename || '').split('.').pop().toUpperCase()} · Uploaded {formatDate(resume.file.created_at)} · {formatBytes(resume.file.byte_size)}
                    </div>
                  </div>
                </div>
                <div className="resume-actions">
                  <button type="button" className="btn btn-secondary" onClick={handleViewResume}>
                    <NwIcon name="external" /> View Resume
                  </button>
                  <button type="button" className="btn btn-primary" onClick={handleDownloadResume}>
                    <NwIcon name="download" /> Download Resume
                  </button>
                </div>
              </>
            ) : (
              <p className="muted" style={{ margin: 0 }}>
                No resume uploaded yet. <Link to="/candidate/resume" className="link">Upload Resume</Link> to help recruiters understand your skills and experience.
              </p>
            )}
          </div>
        </>
      )}

      {editing && (
        <div className="card card-pad" style={{ marginTop: 16 }}>
          <div className="card-head">
            <div>
              <div className="eyebrow">Edit</div>
              <h2 className="card-title">Update your profile</h2>
            </div>
          </div>
          <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
            <label>Full name
              <input className="input" value={form.full_name || ''} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </label>
            <label>Email
              <input className="input" value={form.email || ''} readOnly disabled />
            </label>
            <label>Phone
              <input className="input" value={form.phone || ''} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
            </label>
            <label>Location
              <input className="input" value={form.location || ''} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Bengaluru, Karnataka, India" />
            </label>
            <label>Skills (comma separated)
              <input className="input" value={form.skills || ''} onChange={(e) => setForm({ ...form, skills: e.target.value })} />
            </label>
            <label>Education
              <input className="input" value={form.education || ''} onChange={(e) => setForm({ ...form, education: e.target.value })} />
            </label>
            <label>Experience years
              <input className="input" type="number" value={form.experience_years ?? ''} onChange={(e) => setForm({ ...form, experience_years: e.target.value })} />
            </label>
            <div style={{ display: 'flex', gap: 8, marginTop: 4 }}>
              <button className="btn btn-primary" disabled={saving} onClick={save}>
                {saving ? 'Saving…' : 'Save Changes'}
              </button>
              <button className="btn btn-secondary" disabled={saving} onClick={cancelEdit}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
