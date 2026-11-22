import { getAccessToken, signOut } from './auth'

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
).replace(/\/+$/, '')

let handlingUnauthorized = false

async function handleUnauthorized() {
  if (handlingUnauthorized) return
  handlingUnauthorized = true
  try {
    await signOut()
  } catch {
    handlingUnauthorized = false
  }
  const path = window.location.pathname
  if (path.startsWith('/login') || path.startsWith('/register')) return
  window.location.replace('/login')
}

export class ApiError extends Error {
  constructor(message, status = 0, aborted = false) {
    super(message)
    this.name = aborted ? 'AbortError' : 'ApiError'
    this.status = status
    this.aborted = aborted
  }
}

function detailToMessage(detail, status) {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item
        if (item && typeof item.msg === 'string') {
          const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
          return field ? `${field}: ${item.msg}` : item.msg
        }
        return null
      })
      .filter(Boolean)
    if (messages.length > 0) return messages.join(' ')
  }
  if (status === 401) return 'Your session is invalid or has expired. Please log in again.'
  if (status === 403) return 'You do not have permission to perform this action.'
  if (status === 404) return 'The requested record was not found.'
  if (status >= 500) return 'The server could not complete the request. Please try again.'
  return `Request failed (HTTP ${status}).`
}

export async function apiRequest(path, options = {}) {
  const { method = 'GET', body, auth = true, headers = {}, signal } = options

  const requestHeaders = { Accept: 'application/json', ...headers }
  let payload

  if (auth) {
    const token = await getAccessToken()
    if (!token) {
      throw new ApiError('You need to log in to continue.', 401)
    }
    requestHeaders.Authorization = `Bearer ${token}`
  }

  if (body !== undefined) {
    requestHeaders['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }

  let response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: requestHeaders,
      body: payload,
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('The request was cancelled.', 0, true)
    }
    throw new ApiError(
      `Could not reach the API server at ${API_BASE_URL}. Check that the backend is running and reachable from this browser.`,
      0,
    )
  }

  if (response.status === 204) return null

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
    if (response.status === 401 && auth !== false) {
      await handleUnauthorized()
    }
    const detail =
      data && typeof data === 'object' && 'detail' in data ? data.detail : null
    throw new ApiError(detailToMessage(detail, response.status), response.status)
  }

  return data
}

export { API_BASE_URL }
