export function chatTimeLabel(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function sessionTimeLabel(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''

  const today = new Date()
  if (date.toDateString() === today.toDateString()) {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return date.toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export function toChatMessage(message) {
  return {
    id: message.id,
    role: message.role === 'user' ? 'user' : 'assistant',
    text: message.content ?? '',
    sources: Array.isArray(message.sources) ? message.sources : [],
    hasEvidence: message.has_evidence !== false,
    time: chatTimeLabel(message.created_at),
    createdAt: message.created_at || '',
  }
}

export function moveSessionToTop(sessions, sessionId, updatedAt) {
  const target = sessions.find((session) => session.id === sessionId)
  if (!target) return sessions

  const next = { ...target, updated_at: updatedAt || new Date().toISOString() }
  return [next, ...sessions.filter((session) => session.id !== sessionId)]
}
