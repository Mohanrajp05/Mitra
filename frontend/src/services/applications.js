import { getAccessToken } from './auth'
import { API_BASE_URL } from './api'

async function request(path, options = {}) {
  const token = await getAccessToken()
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  if (!res.ok) throw new Error(`Request failed: ${res.status}`)
  return res.json()
}

export async function listApplicants(jobId) {
  return request(`/api/jobs/${jobId}/applicants`)
}
export async function updateApplicationStatus(applicationId, status) {
  return request(`/api/applications/${applicationId}`, { method: 'PATCH', body: JSON.stringify({ status }) })
}
