import { Link } from 'react-router-dom'

export default function JobCard({ job, onDelete, deleting = false }) {
  return (
    <article className="card job-card">
      <div className="card-topline">
        <span className={`badge ${job.status === 'open' ? 'badge-open' : 'badge-closed'}`}>
          {job.status === 'open' ? 'Open' : 'Closed'}
        </span>
        <span className="card-date">
          {new Date(job.created_at).toLocaleDateString()}
        </span>
      </div>

      <h3 className="card-title">
        <Link to={`/jobs/${job.id}`}>{job.title}</Link>
      </h3>
      <p className="card-subtitle">{job.company || 'Company not specified'}</p>
      <p className="card-description">{job.description}</p>

      {job.required_skills?.length > 0 && (
        <ul className="chip-list" aria-label="Required skills">
          {job.required_skills.slice(0, 6).map((skill) => (
            <li key={skill} className="chip">
              {skill}
            </li>
          ))}
        </ul>
      )}

      <dl className="card-meta">
        <div>
          <dt>Experience</dt>
          <dd>
            {job.experience_required === null || job.experience_required === undefined
              ? 'Not specified'
              : `${job.experience_required} years`}
          </dd>
        </div>
        <div>
          <dt>Location</dt>
          <dd>{job.location || 'Not specified'}</dd>
        </div>
      </dl>

      <div className="card-actions">
        <Link className="btn btn-secondary btn-sm" to={`/jobs/${job.id}`}>
          View details
        </Link>
        <Link className="btn btn-secondary btn-sm" to={`/jobs/${job.id}/edit`}>
          Edit
        </Link>
        <button
          type="button"
          className="btn btn-danger btn-sm"
          onClick={() => onDelete(job)}
          disabled={deleting}
        >
          {deleting ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </article>
  )
}
