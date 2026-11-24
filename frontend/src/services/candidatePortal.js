import { getAccessToken } from './auth'
import { API_BASE_URL, ApiError } from './api'

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

export async function onboardCandidate(payload) {
  return request('/api/candidate/onboard', { method: 'POST', body: JSON.stringify(payload) })
}
export async function getCandidateProfile() {
  return request('/api/candidate/me')
}
export async function updateCandidateProfile(payload) {
  return request('/api/candidate/me', { method: 'PUT', body: JSON.stringify(payload) })
}
export async function getCandidateDashboard() {
  return request('/api/candidate/dashboard')
}
export async function getResume() {
  return request('/api/candidate/resume')
}
export async function uploadResume(file) {
  const token = await getAccessToken()
  if (!token) throw new ApiError('You need to log in to continue.', 401)

  const formData = new FormData()
  formData.append('file', file)

  let response
  try {
    response = await fetch(`${API_BASE_URL}/api/candidate/resume`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    })
  } catch {
    throw new ApiError(
      'Could not reach the API server. Make sure FastAPI is running on port 8000.',
      0,
    )
  }

  const text = await response.text()
  let data = null
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = text
    }
  }

  if (!response.ok) {
    const detail =
      data && typeof data === 'object' && 'detail' in data ? data.detail : null
    const message =
      typeof detail === 'string'
        ? detail
        : `Upload failed (HTTP ${response.status}).`
    throw new ApiError(message, response.status)
  }

  return data
}
export async function removeResume() {
  return request('/api/candidate/resume', { method: 'DELETE' })
}
export async function listCandidateJobs() {
  return request('/api/candidate/jobs')
}
export async function getCandidateJob(jobId) {
  return request(`/api/candidate/jobs/${jobId}`)
}
export async function applyToJob(jobId) {
  return request(`/api/candidate/jobs/${jobId}/apply`, { method: 'POST' })
}
export async function listMyApplications() {
  return request('/api/candidate/applications')
}
export async function listMyInterviews() {
  return request('/api/candidate/interviews')
}
export async function acceptInterview(id) {
  return request(`/api/candidate/interviews/${id}/accept`, { method: 'POST' })
}
export async function declineInterview(id, reason) {
  return request(`/api/candidate/interviews/${id}/decline`, { method: 'POST', body: JSON.stringify({ reason }) })
}
export async function requestReschedule(id, payload) {
  return request(`/api/candidate/interviews/${id}/reschedule-request`, { method: 'POST', body: JSON.stringify(payload) })
}
