import { apiRequest } from './api'

export function listCandidates() {
  return apiRequest('/api/candidates')
}

export function getCandidate(candidateId) {
  return apiRequest(`/api/candidates/${encodeURIComponent(candidateId)}`)
}

export function createCandidate(payload) {
  return apiRequest('/api/candidates', { method: 'POST', body: payload })
}

export function updateCandidate(candidateId, payload) {
  return apiRequest(`/api/candidates/${encodeURIComponent(candidateId)}`, {
    method: 'PUT',
    body: payload,
  })
}

export function deleteCandidate(candidateId) {
  return apiRequest(`/api/candidates/${encodeURIComponent(candidateId)}`, {
    method: 'DELETE',
  })
}

export function getConsent(candidateId, consentType = 'resume_processing') {
  const params = new URLSearchParams({ consent_type: consentType })
  return apiRequest(
    `/api/candidates/${encodeURIComponent(candidateId)}/consent?${params}`,
  )
}

export function updateConsent(candidateId, consentType, granted) {
  return apiRequest(
    `/api/candidates/${encodeURIComponent(candidateId)}/consent`,
    {
      method: 'PUT',
      body: { consent_type: consentType, granted },
    },
  )
}
