import { getAccessToken } from './auth'
import { API_BASE_URL } from './api'

/**
 * Ask the backend which role belongs to the current Supabase session.
 * The role is derived server-side from the verified token and the
 * user_roles table — the frontend never supplies its own role.
 */
export async function getMyRole() {
  const token = await getAccessToken()
  if (!token) return { role: null }
  const res = await fetch(`${API_BASE_URL}/api/auth/role`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const error = new Error(`Could not determine account role (${res.status})`)
    error.status = res.status
    throw error
  }
  return res.json()
}
