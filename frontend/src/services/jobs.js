import { apiRequest } from './api'

export function listJobs() {
  return apiRequest('/api/jobs')
}

export function getJob(jobId) {
  return apiRequest(`/api/jobs/${encodeURIComponent(jobId)}`)
}

export function createJob(payload) {
  return apiRequest('/api/jobs', { method: 'POST', body: payload })
}

export function updateJob(jobId, payload) {
  return apiRequest(`/api/jobs/${encodeURIComponent(jobId)}`, {
    method: 'PUT',
    body: payload,
  })
}

export function deleteJob(jobId) {
  return apiRequest(`/api/jobs/${encodeURIComponent(jobId)}`, {
    method: 'DELETE',
  })
}

export function bulkDeleteJobs(ids) {
  return apiRequest('/api/jobs/bulk-delete', { method: 'POST', body: { ids } })
}
