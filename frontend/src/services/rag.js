import { API_BASE_URL, ApiError, apiRequest } from './api'
import { getAccessToken } from './auth'

export async function uploadDocument(file, sourceType, candidateId, jobId) {
  const token = await getAccessToken()
  if (!token) {
    throw new ApiError('You need to log in to continue.', 401)
  }

  const formData = new FormData()
  formData.append('file', file)
  formData.append('source_type', sourceType)
  if (candidateId) formData.append('candidate_id', candidateId)
  if (jobId) formData.append('job_id', jobId)

  let response
  try {
    response = await fetch(`${API_BASE_URL}/api/rag/documents`, {
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

export function listDocuments() {
  return apiRequest('/api/rag/documents')
}

/**
 * Fetch a document's original file through the authenticated backend
 * endpoint and return it as a Blob (never a raw storage URL).
 */
export async function fetchDocumentFile(documentId) {
  const token = await getAccessToken()
  if (!token) {
    throw new ApiError('You need to log in to continue.', 401)
  }
  let response
  try {
    response = await fetch(
      `${API_BASE_URL}/api/rag/documents/${encodeURIComponent(documentId)}/file`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
  } catch {
    throw new ApiError('Could not reach the API server.', 0)
  }
  if (!response.ok) {
    throw new ApiError(
      `Could not retrieve the document (HTTP ${response.status}).`,
      response.status,
    )
  }
  const disposition = response.headers.get('Content-Disposition') || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i)
  const filename = match ? decodeURIComponent(match[1]) : 'resume'
  return { blob: await response.blob(), filename, mimeType: response.headers.get('Content-Type') || 'application/octet-stream' }
}

export function deleteDocument(documentId) {
  return apiRequest(`/api/rag/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  })
}

const QUERY_TIMEOUT_MS = 90_000
const MATCH_TIMEOUT_MS = 120_000

export function queryRag(query) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), QUERY_TIMEOUT_MS)

  return apiRequest('/api/rag/query', {
    method: 'POST',
    body: { query },
    signal: controller.signal,
  }).finally(() => clearTimeout(timeout))
}

export function analyzeJob(jobId) {
  return apiRequest(`/api/rag/jobs/${encodeURIComponent(jobId)}/analysis`, {
    method: 'POST',
  })
}

export function matchCandidate(candidateId, jobId, options = {}) {
  const { forceRefresh = false, signal } = options
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), MATCH_TIMEOUT_MS)
  const onAbort = () => controller.abort()
  if (signal) {
    if (signal.aborted) controller.abort()
    else signal.addEventListener('abort', onAbort, { once: true })
  }
  const body = { job_id: jobId }
  if (forceRefresh) body.force_refresh = true
  return apiRequest(
    `/api/rag/candidates/${encodeURIComponent(candidateId)}/match`,
    {
      method: 'POST',
      body,
      signal: controller.signal,
    },
  ).finally(() => {
    clearTimeout(timeout)
    if (signal) signal.removeEventListener('abort', onAbort)
  })
}

export function draftCommunication(payload) {
  return apiRequest('/api/rag/communication', { method: 'POST', body: payload })
}

export function scheduleSuggestions(payload) {
  return apiRequest('/api/rag/interview-schedule', {
    method: 'POST',
    body: payload,
  })
}
