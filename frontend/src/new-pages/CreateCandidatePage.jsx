import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Shell from '../mitra/Shell'
import { createCandidate } from '../services/candidates'
import { ApiError } from '../services/api'

const emptyForm = {
  full_name: '',
  email: '',
  phone: '',
  skills: '',
  experience_years: '',
  education: '',
  resume_text: '',
}

export default function CreateCandidatePage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.full_name.trim()) {
      setError('Full name is required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const payload = {
        full_name: form.full_name.trim(),
      }
      if (form.email.trim()) payload.email = form.email.trim()
      if (form.phone.trim()) payload.phone = form.phone.trim()
      if (form.skills.trim()) {
        payload.skills = form.skills
          .split(',')
          .map((skill) => skill.trim())
          .filter(Boolean)
      }
      const experience = String(form.experience_years).trim()
      if (experience) payload.experience_years = Number(experience)
      if (form.education.trim()) payload.education = form.education.trim()
      if (form.resume_text.trim()) payload.resume_text = form.resume_text.trim()

      const created = await createCandidate(payload)
      navigate(
        created && created.id ? `/candidates/${created.id}` : '/candidates'
      )
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : 'Could not create the candidate. Please try again.'
      )
      setSaving(false)
    }
  }

  return (
    <Shell>
      <p className="crumbs">
        <Link to="/candidates">Candidates</Link> / <span>New candidate</span>
      </p>

      <div className="page-head">
        <div>
          <p className="eyebrow">Talent pool</p>
          <h1>Create a candidate</h1>
          <p className="sub">
            Add a candidate profile. You can upload their resume from the
            candidate profile page afterward.
          </p>
        </div>
      </div>

      <section className="card form-card" style={{ maxWidth: 720 }}>
        <form className="form-grid" onSubmit={submit}>
          <div>
            <label htmlFor="cc-full-name">Full name</label>
            <input
              id="cc-full-name"
              value={form.full_name}
              onChange={(e) => update('full_name', e.target.value)}
              placeholder="e.g. Jane Doe"
              required
            />
          </div>
          <div>
            <label htmlFor="cc-email">Email</label>
            <input
              id="cc-email"
              type="email"
              value={form.email}
              onChange={(e) => update('email', e.target.value)}
              placeholder="jane.doe@example.com"
            />
          </div>
          <div>
            <label htmlFor="cc-phone">Phone</label>
            <input
              id="cc-phone"
              value={form.phone}
              onChange={(e) => update('phone', e.target.value)}
              placeholder="+1 555 000 0000"
            />
          </div>
          <div className="span-2">
            <label htmlFor="cc-skills">Skills (comma separated)</label>
            <input
              id="cc-skills"
              value={form.skills}
              onChange={(e) => update('skills', e.target.value)}
              placeholder="e.g. Python, FastAPI, PostgreSQL"
            />
          </div>
          <div>
            <label htmlFor="cc-exp">Experience (years)</label>
            <input
              id="cc-exp"
              type="number"
              min="0"
              max="60"
              step="1"
              value={form.experience_years}
              onChange={(e) => update('experience_years', e.target.value)}
              placeholder="e.g. 3"
            />
          </div>
          <div>
            <label htmlFor="cc-education">Education</label>
            <input
              id="cc-education"
              value={form.education}
              onChange={(e) => update('education', e.target.value)}
              placeholder="e.g. B.Tech Computer Science"
            />
          </div>
          <div className="span-2">
            <label htmlFor="cc-resume">Resume text (optional)</label>
            <textarea
              id="cc-resume"
              rows={8}
              value={form.resume_text}
              onChange={(e) => update('resume_text', e.target.value)}
              placeholder="Paste resume text here…"
            />
          </div>

          {error && (
            <p className="muted span-2" style={{ color: 'var(--danger)' }} role="alert">
              {error}
            </p>
          )}

          <div className="span-2 head-actions" style={{ justifyContent: 'flex-end' }}>
            <Link to="/candidates" className="outline-btn">
              Cancel
            </Link>
            <button type="submit" className="primary-btn" disabled={saving}>
              {saving ? 'Creating…' : 'Create candidate'}
            </button>
          </div>
        </form>
      </section>
    </Shell>
  )
}