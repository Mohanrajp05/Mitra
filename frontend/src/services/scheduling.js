import { apiRequest } from './api'

export function listScheduledInterviews({ date_from, date_to } = {}) {
  const params = new URLSearchParams()
  if (date_from) params.set('date_from', date_from)
  if (date_to) params.set('date_to', date_to)
  const query = params.toString()
  return apiRequest(`/api/scheduled-interviews${query ? `?${query}` : ''}`)
}

export function getScheduledInterview(interviewId) {
  return apiRequest(`/api/scheduled-interviews/${encodeURIComponent(interviewId)}`)
}

export function getInterviewAvailability(candidateId, interviewDate) {
  const params = new URLSearchParams({ interview_date: interviewDate })
  return apiRequest(
    `/api/scheduled-interviews/availability?candidate_id=${encodeURIComponent(candidateId)}&${params}`,
  )
}

export function createScheduledInterview(payload) {
  return apiRequest('/api/scheduled-interviews', { method: 'POST', body: payload })
}

export function updateScheduledInterview(interviewId, payload) {
  return apiRequest(`/api/scheduled-interviews/${encodeURIComponent(interviewId)}`, {
    method: 'PATCH',
    body: payload,
  })
}
