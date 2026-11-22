import { Link } from 'react-router-dom'
import Shell from '../../mitra/Shell'
import Icon from '../../mitra/Icons'

const starts = [
  { icon: 'mail', title: 'Paste a job description', body: 'Drop in any JD and Mitra will structure it for you.' },
  { icon: 'upload', title: 'Import from job boards', body: 'Bring roles from LinkedIn, Naukri or a CSV file.' },
  { icon: 'spark', title: 'Start from a template', body: '40+ ready templates for tech, design and ops roles.' },
]

export default function JobsEmptyPage() {
  return (
    <Shell>
      <div className="page-head">
        <div>
          <p className="eyebrow">Hiring</p>
          <h1>Jobs</h1>
          <p className="sub">Every role you’re hiring for, with Mitra’s match insights at a glance.</p>
        </div>
        <Link to="/jobs/new" className="primary-btn">
          <Icon name="plus" size={16} /> Create job
        </Link>
      </div>

      <section className="card empty-hero">
        <div className="empty-art" aria-hidden="true">
          <div className="case" />
          <div className="glass" />
        </div>
        <h2>No jobs yet — let’s post your first role</h2>
        <p>Describe the role in your own words. Mitra will pull out skills, seniority and experience so you can start matching candidates right away.</p>
        <div className="head-actions center">
          <Link to="/jobs/new" className="primary-btn">
            <Icon name="plus" size={16} /> Create job
          </Link>
          <Link to="/assistant" className="outline-btn">
            <Icon name="spark" size={16} /> Draft with Mitra
          </Link>
        </div>
      </section>

      <p className="eyebrow spaced">Other ways to start</p>
      <section className="start-grid">
        {starts.map((item) => (
          <article key={item.title} className="card start-card">
            <span className="stat-icon">
              <Icon name={item.icon} size={18} />
            </span>
            <h3>{item.title}</h3>
            <p>{item.body}</p>
          </article>
        ))}
      </section>
    </Shell>
  )
}
