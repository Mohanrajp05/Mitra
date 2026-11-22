import { apiRequest } from './api'

export function checkHealth() {
  return apiRequest('/api/health', { auth: false })
}
