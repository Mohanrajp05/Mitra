import { useEffect, useRef, useState } from 'react'
import Icon from './Icons'
import {
  getUnreadCount,
  listNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from '../services/notifications'

const TYPE_LABEL = { '24_hour': '24 hours before', '1_hour': '1 hour before' }

function formatMoment(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit',
  })
}

function formatInterview(item) {
  if (!item.interview_date) return ''
  const date = new Date(`${item.interview_date}T00:00:00`)
  const day = Number.isNaN(date.getTime())
    ? item.interview_date
    : date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  const time = item.start_time ? String(item.start_time).slice(0, 5) : ''
  return `${day}${time ? ` · ${time}` : ''}`
}

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [count, setCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const containerRef = useRef(null)

  async function refresh() {
    setLoading(true)
    try {
      const [list, unread] = await Promise.all([listNotifications(), getUnreadCount()])
      setItems(Array.isArray(list) ? list : [])
      setCount(Number(unread?.count) || 0)
      setError('')
    } catch (err) {
      setError(err?.message || 'Could not load notifications.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    getUnreadCount()
      .then((result) => setCount(Number(result?.count) || 0))
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!open) return undefined
    refresh()
    function onPointerDown(event) {
      if (containerRef.current && !containerRef.current.contains(event.target)) {
        setOpen(false)
      }
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  async function readOne(item) {
    try {
      await markNotificationRead(item.id)
      await refresh()
    } catch (err) {
      setError(err?.message || 'Could not mark the notification as read.')
    }
  }

  async function readAll() {
    try {
      await markAllNotificationsRead()
      await refresh()
    } catch (err) {
      setError(err?.message || 'Could not mark notifications as read.')
    }
  }

  return (
    <div className="notification-bell" ref={containerRef}>
      <button
        type="button"
        className="icon-btn notification-trigger"
        aria-label={`Notifications${count ? `, ${count} unread` : ''}`}
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <Icon name="bell" size={16} />
        {count > 0 && <span className="notification-badge">{count > 9 ? '9+' : count}</span>}
      </button>

      {open && (
        <section className="notification-panel" aria-label="Notifications">
          <header className="notification-head">
            <strong>Notifications</strong>
            <button type="button" className="notification-read-all" onClick={readAll} disabled={count === 0 || loading}>
              Mark all as read
            </button>
          </header>
          {error && <p className="notification-error">{error}</p>}
          {loading && <p className="notification-empty">Loading notifications…</p>}
          {!loading && items.length === 0 && <p className="notification-empty">No new notifications.</p>}
          <ul className="notification-list">
            {items.map((item) => (
              <li key={item.id} className={`notification-item ${item.status}`}>
                <div className="notification-item-top">
                  <strong>{item.title}</strong>
                  <span className={`notification-status status-${item.status}`}>{item.status}</span>
                </div>
                <p className="notification-copy">{item.message}</p>
                <p className="notification-meta">
                  {item.candidate_name || 'Candidate'} · {formatInterview(item)}
                </p>
                <p className="notification-meta">
                  {TYPE_LABEL[item.notification_type] || item.notification_type} · Generated {formatMoment(item.created_at || item.scheduled_at)}
                </p>
                {item.status === 'sent' && (
                  <button type="button" className="notification-read" onClick={() => readOne(item)}>
                    <Icon name="check" size={13} /> Mark as read
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}
