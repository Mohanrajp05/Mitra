import { useEffect, useMemo, useState } from 'react'
import { getAccessToken } from '../services/auth'
import { API_BASE_URL } from '../services/api'

async function request(path, options = {}) {
  const token = await getAccessToken()
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
  })
  if (!res.ok) throw new Error(`Request failed: ${res.status}`)
  return res.json()
}

function formatTime(value) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })
}

export default function RecruiterConversationsPage() {
  const [convs, setConvs] = useState([])
  const [active, setActive] = useState(null)
  const [msgs, setMsgs] = useState([])
  const [text, setText] = useState('')
  const [candidateId, setCandidateId] = useState('')
  const [applicationId, setApplicationId] = useState('')
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function loadConversations() {
    const rows = await request('/api/conversations')
    setConvs(Array.isArray(rows) ? rows : [])
    return Array.isArray(rows) ? rows : []
  }

  useEffect(() => {
    let alive = true
    loadConversations().catch((e) => alive && setError(e.message))
    const timer = setInterval(() => {
      if (alive) loadConversations().catch(() => {})
    }, 20000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [])

  async function startConv() {
    if (!candidateId.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const conversation = await request('/api/conversations', {
        method: 'POST',
        body: JSON.stringify({
          candidate_id: candidateId.trim(),
          application_id: applicationId.trim() || null,
        }),
      })
      await loadConversations()
      setActive(conversation)
      setMsgs([])
      setCandidateId('')
      setApplicationId('')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function openConv(conversation) {
    setActive(conversation)
    setError('')
    try {
      const messages = await request(`/api/conversations/${conversation.id}/messages`)
      setMsgs(Array.isArray(messages) ? messages : [])
      await loadConversations()
    } catch (e) {
      setError(e.message)
    }
  }

  async function send() {
    if (!active || !text.trim() || busy) return
    setBusy(true)
    setError('')
    try {
      const message = await request(`/api/conversations/${active.id}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: text }),
      })
      setMsgs((prev) => [...prev, message])
      setText('')
      await loadConversations()
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase()
    if (!query) return convs
    return convs.filter((conversation) =>
      [conversation.candidate_name, conversation.candidate_email, conversation.job_title, conversation.application_id]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(query)),
    )
  }, [convs, filter])

  const unreadTotal = convs.reduce((sum, conversation) => sum + Number(conversation.unread_count || 0), 0)

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Candidate conversations</div>
          <h1 className="page-title">Conversations</h1>
          <p className="page-sub">
            Direct chat with candidates. AI email drafting still lives in the Messages section.
            {unreadTotal > 0 ? ` ${unreadTotal} unread candidate message${unreadTotal === 1 ? '' : 's'}.` : ''}
          </p>
        </div>
      </header>

      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}

      <div className="dash-grid">
        <aside className="card card-pad" aria-label="Candidate conversations">
          <div className="card-head">
            <div>
              <div className="eyebrow">Inbox</div>
              <h2 className="card-title">Conversations</h2>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
            <input className="input" placeholder="Candidate ID" value={candidateId} onChange={(e) => setCandidateId(e.target.value)} />
            <input className="input" placeholder="Application ID (optional)" value={applicationId} onChange={(e) => setApplicationId(e.target.value)} />
            <button className="btn btn-secondary" onClick={startConv} disabled={!candidateId.trim() || busy}>Start conversation</button>
            <input className="input" placeholder="Search by candidate, job, application…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          </div>

          {filtered.length === 0 ? (
            <p className="muted">No conversations match.</p>
          ) : (
            <ul className="cand-list" style={{ gap: 6 }}>
              {filtered.map((conversation) => (
                <li key={conversation.id}>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => openConv(conversation)}
                    style={{
                      width: '100%',
                      display: 'flex',
                      textAlign: 'left',
                      justifyContent: 'space-between',
                      gap: 10,
                      padding: '10px 12px',
                      borderColor: active?.id === conversation.id ? 'var(--primary)' : undefined,
                      background: Number(conversation.unread_count) > 0 ? 'var(--primary-soft)' : undefined,
                    }}
                  >
                    <span style={{ minWidth: 0, display: 'grid', gap: 2 }}>
                      <strong style={{ fontSize: 13 }}>{conversation.candidate_name || conversation.candidate_email || 'Candidate'}</strong>
                      <span className="muted" style={{ fontSize: 11.5 }}>{conversation.job_title || 'General conversation'}</span>
                      <span className="muted" style={{ fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {conversation.last_message || 'No messages yet'}
                      </span>
                      <span className="muted" style={{ fontSize: 10.5 }}>{formatTime(conversation.last_message_at || conversation.updated_at)}</span>
                    </span>
                    {Number(conversation.unread_count) > 0 && (
                      <span className="nav-count" title={`${conversation.unread_count} unread`}>{conversation.unread_count}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="card card-pad" aria-label="Message history">
          <div className="card-head">
            <div>
              <div className="eyebrow">Conversation</div>
              <h2 className="card-title">{active ? active.candidate_name || 'Candidate' : 'Select a conversation'}</h2>
              {active?.job_title && <p className="muted" style={{ fontSize: 11.5 }}>{active.job_title}</p>}
              {active?.application_id && <p className="muted" style={{ fontSize: 11.5 }}>Application: {active.application_id}</p>}
            </div>
          </div>

          <div style={{ minHeight: 280, maxHeight: 420, overflowY: 'auto', display: 'grid', gap: 10, marginBottom: 14 }}>
            {!active && <p className="muted">Choose a conversation to read its history.</p>}
            {active && msgs.length === 0 && <p className="muted">No messages in this conversation yet.</p>}
            {msgs.map((message) => {
              const mine = message.sender_role === 'recruiter'
              return (
                <div
                  key={message.id}
                  style={{
                    justifySelf: mine ? 'end' : 'start',
                    maxWidth: '82%',
                    padding: '8px 12px',
                    borderRadius: 12,
                    background: mine ? 'var(--primary-soft)' : 'var(--surface-2)',
                    color: 'var(--text)',
                  }}
                >
                  <div style={{ fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', opacity: 0.7 }}>
                    {mine ? 'You' : 'Candidate'}
                  </div>
                  <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{message.content}</div>
                  <div className="muted" style={{ fontSize: 10.5, marginTop: 4 }}>
                    {formatTime(message.sent_at)}
                    {mine && message.read_at ? ' · Read' : ''}
                  </div>
                </div>
              )
            })}
          </div>

          <div style={{ display: 'flex', gap: 8 }}>
            <input
              className="input"
              style={{ flex: 1 }}
              placeholder={active ? 'Write a message…' : 'Select a conversation first'}
              value={text}
              disabled={!active || busy}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  send()
                }
              }}
            />
            <button className="btn btn-primary" onClick={send} disabled={!active || !text.trim() || busy}>
              {busy ? 'Sending…' : 'Send'}
            </button>
          </div>
        </section>
      </div>
    </div>
  )
}
