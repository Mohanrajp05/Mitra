import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Shell from '../../mitra/Shell'
import { createJob } from '../../services/jobs'
import { ApiError } from '../../services/api'

const emptyForm = {
  title: '',
  company: '',
  location: '',
  description: '',
  required_skills: '',
  experience_required: '',
  status: 'open',
  experience_level: '',
  job_type: '',
  internship_duration_months: '',
  compensation_type: '',
  salary_stipend: '',
  work_mode: '',
  required_documents: '',
  application_deadline: '',
}

export default function CreateJobPage() {
  const navigate = useNavigate()
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  function update(field, value) {
    setForm((current) => ({ ...current, [field]: value }))
  }

  async function submit(event) {
    event.preventDefault()
    if (!form.title.trim() || !form.description.trim()) {
      setError('Job title and description are required.')
      return
    }
    setSaving(true)
    setError('')
    try {
      const experience = String(form.experience_required).trim()
      const payload = {
        title: form.title.trim(),
        description: form.description,
        required_skills: form.required_skills
          .split(',')
          .map((skill) => skill.trim())
          .filter(Boolean),
        status: form.status,
      }
      if (form.company.trim()) payload.company = form.company.trim()
      if (form.location.trim()) payload.location = form.location.trim()
      if (experience) payload.experience_required = Number(experience)
      if (form.experience_level) payload.experience_level = form.experience_level
      if (form.job_type) payload.job_type = form.job_type
      if (form.internship_duration_months) payload.internship_duration_months = Number(form.internship_duration_months)
      if (form.compensation_type) payload.compensation_type = form.compensation_type
      if (form.salary_stipend.trim()) payload.salary_stipend = form.salary_stipend.trim()
      if (form.work_mode) payload.work_mode = form.work_mode
      if (form.required_documents.trim()) payload.required_documents = form.required_documents.split(',').map((d) => d.trim()).filter(Boolean)
      if (form.application_deadline) payload.application_deadline = form.application_deadline
      const created = await createJob(payload)
      navigate(created && created.id ? `/jobs/${created.id}` : '/jobs')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create the job. Please try again.')
      setSaving(false)
    }
  }

  return (
    <Shell>
      <p className="crumbs">
        <Link to="/jobs">Jobs</Link> / <span>New job</span>
      </p>

      <div className="page-head">
        <div>
          <p className="eyebrow">Hiring</p>
          <h1>Create a job</h1>
          <p className="sub">Describe the role. Mitra parses the description into requirements and starts matching resumes.</p>
        </div>
      </div>

      <section className="card form-card" style={{ maxWidth: 720 }}>
        <form className="form-grid" onSubmit={submit}>
          <div>
            <label htmlFor="cj-title">Job title</label>
            <input
              id="cj-title"
              value={form.title}
              onChange={(e) => update('title', e.target.value)}
              placeholder="e.g. Backend Engineer"
              required
            />
          </div>
          <div>
            <label htmlFor="cj-company">Company</label>
            <input
              id="cj-company"
              value={form.company}
              onChange={(e) => update('company', e.target.value)}
              placeholder="Company name"
            />
          </div>
          <div>
            <label htmlFor="cj-location">Location</label>
            <input
              id="cj-location"
              value={form.location}
              onChange={(e) => update('location', e.target.value)}
              placeholder="e.g. Remote, Bengaluru"
            />
          </div>
          <div>
            <label htmlFor="cj-exp">Experience required (years)</label>
            <input
              id="cj-exp"
              type="number"
              min="0"
              max="50"
              step="1"
              value={form.experience_required}
              onChange={(e) => update('experience_required', e.target.value)}
              placeholder="e.g. 3"
            />
          </div>
          <div>
            <label htmlFor="cj-status">Status</label>
            <select id="cj-status" value={form.status} onChange={(e) => update('status', e.target.value)}>
              <option value="open">Open</option>
              <option value="closed">Closed</option>
            </select>
          </div>
          <div>
            <label htmlFor="cj-exp-level">Experience level</label>
            <select id="cj-exp-level" value={form.experience_level} onChange={(e) => update('experience_level', e.target.value)}>
              <option value="">Not specified</option>
              <option value="ALL">ALL</option>
              <option value="Fresher">Fresher</option>
              <option value="Internship">Internship</option>
              <option value="Experienced">Experienced</option>
            </select>
          </div>
          <div>
            <label htmlFor="cj-job-type">Job type</label>
            <select id="cj-job-type" value={form.job_type} onChange={(e) => update('job_type', e.target.value)}>
              <option value="">Not specified</option>
              <option value="Full-time">Full-time</option>
              <option value="Part-time">Part-time</option>
              <option value="Internship">Internship</option>
              <option value="Contract">Contract</option>
            </select>
          </div>
          <div>
            <label htmlFor="cj-duration">Internship duration (months)</label>
            <input id="cj-duration" type="number" min="1" max="24" value={form.internship_duration_months} onChange={(e) => update('internship_duration_months', e.target.value)} placeholder="e.g. 6" />
          </div>
          <div>
            <label htmlFor="cj-comp">Compensation</label>
            <select id="cj-comp" value={form.compensation_type} onChange={(e) => update('compensation_type', e.target.value)}>
              <option value="">Not specified</option>
              <option value="Paid">Paid</option>
              <option value="Unpaid">Unpaid</option>
              <option value="Stipend">Stipend</option>
            </select>
          </div>
          <div>
            <label htmlFor="cj-salary">Salary / Stipend</label>
            <input id="cj-salary" value={form.salary_stipend} onChange={(e) => update('salary_stipend', e.target.value)} placeholder="e.g. ₹10,000/month or 5-8 LPA" />
          </div>
          <div>
            <label htmlFor="cj-workmode">Work mode</label>
            <select id="cj-workmode" value={form.work_mode} onChange={(e) => update('work_mode', e.target.value)}>
              <option value="">Not specified</option>
              <option value="Remote">Remote</option>
              <option value="Hybrid">Hybrid</option>
              <option value="On-site">On-site</option>
            </select>
          </div>
          <div>
            <label htmlFor="cj-deadline">Application deadline</label>
            <input id="cj-deadline" type="date" value={form.application_deadline} onChange={(e) => update('application_deadline', e.target.value)} />
          </div>
          <div className="span-2">
            <label htmlFor="cj-docs">Required documents (comma separated)</label>
            <input id="cj-docs" value={form.required_documents} onChange={(e) => update('required_documents', e.target.value)} placeholder="e.g. Resume, College ID, Portfolio link" />
          </div>
          <div className="span-2">
            <label htmlFor="cj-skills">Required skills (comma separated)</label>
            <input
              id="cj-skills"
              value={form.required_skills}
              onChange={(e) => update('required_skills', e.target.value)}
              placeholder="e.g. Python, FastAPI, PostgreSQL"
            />
          </div>
          <div className="span-2">
            <label htmlFor="cj-desc">Job description</label>
            <textarea
              id="cj-desc"
              rows={10}
              value={form.description}
              onChange={(e) => update('description', e.target.value)}
              placeholder="Paste or write the job description here…"
              required
            />
          </div>

          {error && (
            <p className="muted span-2" style={{ color: 'var(--danger)' }} role="alert">
              {error}
            </p>
          )}

          <div className="span-2 head-actions" style={{ justifyContent: 'flex-end' }}>
            <Link to="/jobs" className="outline-btn">Cancel</Link>
            <button type="submit" className="primary-btn" disabled={saving}>
              {saving ? 'Creating…' : 'Create job'}
            </button>
          </div>
        </form>
      </section>
    </Shell>
  )
}
