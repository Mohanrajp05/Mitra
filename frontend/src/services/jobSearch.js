import { apiRequest } from './api'

export function getJobLink(source, role, location = '', fallback = false) {
  const params = new URLSearchParams({ source, role, location })
  if (fallback) params.set('fallback', 'true')
  return apiRequest(`/job-link?${params.toString()}`, { auth: false })
}
