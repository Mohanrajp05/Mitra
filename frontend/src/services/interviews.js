import { apiRequest } from './api'
import { getAccessToken } from './auth'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/+$/, '')

export function createInterviewSession() {
  return apiRequest('/api/interviews/sessions', { method: 'POST' })
}

export function getCurrentInterviewSession() {
  return apiRequest('/api/interviews/sessions/current')
}

export function getInterviewSession(sessionId) {
  return apiRequest(`/api/interviews/sessions/${encodeURIComponent(sessionId)}`)
}

export function startInterviewSession(sessionId, options = {}) {
  return apiRequest(`/api/interviews/sessions/${encodeURIComponent(sessionId)}/start`, {
    method: 'POST',
    signal: options.signal,
  })
}

export function getInterviewQuestion(sessionId) {
  return apiRequest(`/api/interviews/sessions/${encodeURIComponent(sessionId)}/questions/current`)
}

export function listInterviewQuestions(sessionId) {
  return apiRequest(`/api/interviews/sessions/${encodeURIComponent(sessionId)}/questions`)
}

export function submitInterviewAnswer(sessionId, questionNumber, answerText) {
  return apiRequest(
    `/api/interviews/sessions/${encodeURIComponent(sessionId)}/questions/${questionNumber}/answer`,
    {
      method: 'POST',
      body: { answer_text: answerText },
    },
  )
}

export function completeInterviewSession(sessionId) {
  return apiRequest(
    `/api/interviews/sessions/${encodeURIComponent(sessionId)}/complete`,
    {
      method: 'POST',
    },
  )
}

export async function uploadInterviewResume(sessionId, file) {
  const token = await getAccessToken()
  if (!token) throw new Error('You need to log in to continue.')

  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(
    `${API_BASE_URL}/api/interviews/sessions/${encodeURIComponent(sessionId)}/resume`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData,
    },
  )

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
    const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null
    if (typeof detail === 'string') throw new Error(detail)
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => item?.msg).filter(Boolean)
      if (messages.length) throw new Error(messages.join(' '))
    }
    throw new Error(`Upload failed (HTTP ${response.status}).`)
  }

  return data
}

export function deleteInterviewResume(sessionId) {
  return apiRequest(`/api/interviews/sessions/${encodeURIComponent(sessionId)}/resume`, {
    method: 'DELETE',
  })
}
