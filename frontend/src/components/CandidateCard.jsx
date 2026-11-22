import { Link } from 'react-router-dom'

export default function CandidateCard({ candidate, onDelete, deleting = false }) {
  return (
    <article className="card candidate-card">
      <div className="candidate-avatar" aria-hidden="true">
        {candidate.full_name?.charAt(0)?.toUpperCase() || '?'}
      </div>

      <div className="candidate-card-body">
        <h3 className="card-title">
          <Link to={`/candidates/${candidate.id}`}>{candidate.full_name}</Link>
        </h3>
        <p className="card-subtitle">
          {candidate.email || 'Email not provided'}
        </p>

        {candidate.skills?.length > 0 && (
          <ul className="chip-list" aria-label="Skills">
            {candidate.skills.slice(0, 5).map((skill) => (
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
              {candidate.experience_years === null ||
              candidate.experience_years === undefined
                ? 'Not specified'
                : `${candidate.experience_years} years`}
            </dd>
          </div>
          <div>
            <dt>Education</dt>
            <dd>{candidate.education || 'Not specified'}</dd>
          </div>
        </dl>

        <div className="card-actions">
          <Link className="btn btn-secondary btn-sm" to={`/candidates/${candidate.id}`}>
            View details
          </Link>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            onClick={() => onDelete(candidate)}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : 'Delete'}
          </button>
        </div>
      </div>
    </article>
  )
}
