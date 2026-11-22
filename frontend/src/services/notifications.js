import { apiRequest } from './api'

export function listNotifications() {
  return apiRequest('/api/notifications')
}

export function getUnreadCount() {
  return apiRequest('/api/notifications/unread-count')
}

export function markNotificationRead(reminderId) {
  return apiRequest(`/api/notifications/${encodeURIComponent(reminderId)}/read`, {
    method: 'PATCH',
  })
}

export function markAllNotificationsRead() {
  return apiRequest('/api/notifications/read-all', { method: 'PATCH' })
}
