import { useState } from 'react'
import { getJobLink } from '../services/jobSearch'

function SearchButtons({ role, location }) {
  const [loading, setLoading] = useState('')
  const [error, setError] = useState('')

  async function openSearch(source) {
    setLoading(source)
    setError('')
    try {
      let response
      try {
        response = await getJobLink(source, role, location)
      } catch (primaryError) {
        if (source !== 'naukri') throw primaryError
        response = await getJobLink('naukri', role, location, true)
      }
      const { url } = response
      if (!url) throw new Error('The job search link was unavailable.')
      const tab = window.open(url, '_blank', 'noopener,noreferrer')
      if (!tab) setError('Your browser blocked the new tab. Allow pop-ups and try again.')
    } catch (err) {
      setError(err.message || 'Could not create the job search link.')
    } finally {
      setLoading('')
    }
  }

  return (
    <div className="job-search-role">
      <strong>{role}</strong>
      {location && <span className="muted">{location}</span>}
      <div className="job-search-actions">
        <button type="button" className="btn btn-secondary" disabled={Boolean(loading)} onClick={() => openSearch('linkedin')}>
          {loading === 'linkedin' ? 'Opening…' : 'Search on LinkedIn'}
        </button>
        <button type="button" className="btn btn-secondary" disabled={Boolean(loading)} onClick={() => openSearch('naukri')}>
          {loading === 'naukri' ? 'Opening…' : 'Search on Naukri'}
        </button>
      </div>
      {error && <p className="job-search-error" role="alert">{error}</p>}
    </div>
  )
}

export default function JobSearch({ role, location = '', roles = [] }) {
  const entries = roles.length > 0
    ? roles.map((item) => typeof item === 'string' ? { role: item, location } : item)
    : role ? [{ role, location }] : []

  if (entries.length === 0) return null
  return <div className="job-search-list">{entries.map((entry) => <SearchButtons key={`${entry.role}-${entry.location || ''}`} {...entry} />)}</div>
}
