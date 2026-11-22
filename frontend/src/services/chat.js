import { apiRequest } from './api'

export function listChatSessions() {
  return apiRequest('/api/chat/sessions')
}

export function createChatSession(title) {
  return apiRequest('/api/chat/sessions', {
    method: 'POST',
    body: title ? { title } : {},
  })
}

export function renameChatSession(sessionId, title) {
  return apiRequest(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'PATCH',
    body: { title },
  })
}

export function deleteChatSession(sessionId) {
  return apiRequest(`/api/chat/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  })
}

export function deleteAllChatSessions() {
  return apiRequest('/api/chat/sessions', { method: 'DELETE' })
}

export function listChatMessages(sessionId) {
  return apiRequest(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
  )
}

const MESSAGE_TIMEOUT_MS = 90_000

export function sendChatMessage(sessionId, content, options = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), MESSAGE_TIMEOUT_MS)
  const onExternalAbort = () => controller.abort()
  if (options.signal) {
    if (options.signal.aborted) onExternalAbort()
    else options.signal.addEventListener('abort', onExternalAbort, { once: true })
  }
  const body = { content }
  if (options.documentIds?.length) body.document_ids = options.documentIds
  if (options.candidateId) body.candidate_id = options.candidateId
  if (options.jobId) body.job_id = options.jobId
  if (options.jobSearch) body.job_search = true
  if (options.jobPreferences) body.job_preferences = options.jobPreferences

  return apiRequest(
    `/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`,
    {
      method: 'POST',
      body,
      signal: controller.signal,
    },
  ).finally(() => {
    clearTimeout(timeout)
    if (options.signal) options.signal.removeEventListener('abort', onExternalAbort)
  })
}
