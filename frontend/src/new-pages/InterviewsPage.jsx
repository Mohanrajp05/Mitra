import { useCallback, useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import { ApiError } from '../services/api'
import {
  listScheduledInterviews,
  getInterviewAvailability,
  updateScheduledInterview,
} from '../services/scheduling'
import {
  SLOT_MINUTES,
  endOfSlot,
  formatDate,
  formatTime,
  isPastSlot,
  localTimeZone,
  slotTimes,
  todayString,
} from './scheduling'

const STATUS_CHIP = {
  scheduled: 'chip-green',
  completed: 'chip-gray',
  cancelled: 'chip-gray',
  missed: 'chip-gray',
}

function monthDays(anchor) {
  const [year, month] = String(anchor).split('-').map(Number)
  const first = new Date(year, month - 1, 1)
  const start = new Date(first)
  start.setDate(start.getDate() - ((first.getDay() + 6) % 7))
  return Array.from({ length: 42 }, (_, i) => {
    const date = new Date(start)
    date.setDate(start.getDate() + i)
    return date
  })
}

function weekDaysFrom(anchor) {
  const [year, month, day] = String(anchor).split('-').map(Number)
  const base = new Date(year, month - 1, day)
  const monday = new Date(base)
  monday.setDate(base.getDate() - ((base.getDay() + 6) % 7))
  return Array.from({ length: 7 }, (_, i) => {
    const date = new Date(monday)
    date.setDate(monday.getDate() + i)
    return date
  })
}

function labelFor(view, anchor) {
  const date = new Date(`${anchor}T00:00:00`)
  if (view === 'day') return formatDate(anchor)
  if (view === 'month') {
    return date.toLocaleDateString(undefined, { month: 'long', year: 'numeric' })
  }
  const days = weekDaysFrom(anchor)
  const first = days[0]
  const last = days[days.length - 1]
  return `${formatDate(`${first.getFullYear()}-${String(first.getMonth() + 1).padStart(2, '0')}-${String(first.getDate()).padStart(2, '0')}`)} – ${formatDate(`${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, '0')}-${String(last.getDate()).padStart(2, '0')}`)}`
}

function moveAnchor(anchor, view, direction) {
  const [year, month, day] = String(anchor).split('-').map(Number)
  const date = new Date(year, month - 1, day)
  if (view === 'day') date.setDate(date.getDate() + direction)
  else if (view === 'week') date.setDate(date.getDate() + direction * 7)
  else date.setMonth(date.getMonth() + direction)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function dateKey(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export default function InterviewsPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const [view, setView] = useState('week')
  const [anchor, setAnchor] = useState(todayString())
  const [interviews, setInterviews] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState(location.state?.notice || '')
  const [selected, setSelected] = useState(null)
  const [rescheduling, setRescheduling] = useState(null)
  const [resDate, setResDate] = useState(todayString())
  const [resTime, setResTime] = useState('')
  const [resBooked, setResBooked] = useState([])
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const rows = await listScheduledInterviews()
      setInterviews(Array.isArray(rows) ? rows : [])
      setError('')
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not load scheduled interviews.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    window.addEventListener('focus', refresh)
    return () => window.removeEventListener('focus', refresh)
  }, [refresh])

  useEffect(() => {
    if (!notice) return undefined
    const timer = window.setTimeout(() => setNotice(''), 4000)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => {
    if (!rescheduling) return
    let active = true
    getInterviewAvailability(rescheduling.candidate_id, resDate)
      .then((result) => {
        if (active) setResBooked(Array.isArray(result?.booked_slots) ? result.booked_slots.filter((slot) => slot !== rescheduling.start_time) : [])
      })
      .catch(() => { if (active) setResBooked([]) })
    return () => { active = false }
  }, [rescheduling?.id, resDate])

  const byDate = useMemo(() => {
    const grouped = new Map()
    interviews.forEach((item) => {
      const key = String(item.interview_date || '').slice(0, 10)
      if (!grouped.has(key)) grouped.set(key, [])
      grouped.get(key).push(item)
    })
    grouped.forEach((list) => list.sort((a, b) => String(a.start_time).localeCompare(String(b.start_time))))
    return grouped
  }, [interviews])

  const days = useMemo(
    () => (view === 'month' ? monthDays(anchor) : view === 'week' ? weekDaysFrom(anchor) : [new Date(`${anchor}T00:00:00`)]),
    [view, anchor],
  )
  const rescheduleSlots = useMemo(
    () => slotTimes(rescheduling?.duration_minutes || SLOT_MINUTES),
    [rescheduling?.duration_minutes],
  )

  function eventCard(item) {
    return (
      <button
        type="button"
        key={item.id}
        className={`iv-event ${item.status}`}
        onClick={() => setSelected(item)}
        title={`${item.title} · ${item.candidate_name || 'Candidate'}`}
      >
        <strong>{item.candidate_name || 'Candidate'}</strong>
        <span>{formatTime(item.start_time)} – {formatTime(item.end_time || endOfSlot(item.start_time))}</span>
        <span className={`chip ${STATUS_CHIP[item.status] || 'chip-gray'}`}>{item.status}</span>
      </button>
    )
  }

  async function cancelInterview(item) {
    if (!window.confirm(`Cancel the interview with ${item.candidate_name || 'this candidate'}? History will be preserved.`)) return
    setBusy(true)
    try {
      await updateScheduledInterview(item.id, { status: 'cancelled' })
      setSelected(null)
      setNotice('Interview cancelled. History preserved.')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not cancel the interview.')
    } finally {
      setBusy(false)
    }
  }

  function openReschedule(item) {
    setRescheduling(item)
    setResDate(String(item.interview_date))
    setResTime(String(item.start_time))
    setResBooked([])
  }

  async function confirmReschedule() {
    if (!rescheduling || !resTime || isPastSlot(resDate, resTime) || resBooked.includes(resTime)) return
    setBusy(true)
    try {
      await updateScheduledInterview(rescheduling.id, {
        interview_date: resDate,
        start_time: resTime,
        time_zone: localTimeZone(),
      })
      setRescheduling(null)
      setSelected(null)
      setNotice('Interview rescheduled.')
      await refresh()
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not reschedule the interview.')
    } finally {
      setBusy(false)
    }
  }

  const upcoming = interviews.filter((item) => item.status === 'scheduled' && !isPastSlot(item.interview_date, item.start_time))
  const history = interviews.filter((item) => item.status !== 'scheduled' || isPastSlot(item.interview_date, item.start_time))

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Scheduling</div>
          <h1 className="page-title">Interviews</h1>
          <p className="page-sub">Real scheduled interviews, with past history preserved.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-primary" onClick={() => navigate('/interviews/schedule')}>
            <NwIcon name="calendar" /> Schedule interview
          </button>
        </div>
      </header>

      {notice && <p className="as-note" role="status">{notice}</p>}
      {error && <p className="as-note" style={{ color: 'var(--danger)' }}>{error}</p>}

      <div className="iv-toolbar">
        <div className="iv-nav">
          <button type="button" className="icon-btn" aria-label="Previous" onClick={() => setAnchor((a) => moveAnchor(a, view, -1))}><NwIcon name="chevron-left" /></button>
          <strong>{labelFor(view, anchor)}</strong>
          <button type="button" className="icon-btn" aria-label="Next" onClick={() => setAnchor((a) => moveAnchor(a, view, 1))}><NwIcon name="chevron-right" /></button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAnchor(todayString())}>Today</button>
        </div>
        <div className="iv-view" role="group" aria-label="Calendar view">
          {['month', 'week', 'day'].map((name) => (
            <button key={name} type="button" className={view === name ? 'active' : ''} aria-pressed={view === name} onClick={() => setView(name)}>
              {name[0].toUpperCase() + name.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {loading && <p className="muted">Loading interviews…</p>}
      {!loading && (
        <div className={`iv-calendar-view ${view}`}>
          {days.map((date) => {
            const key = dateKey(date)
            const items = byDate.get(key) || []
            const isToday = key === todayString()
            return (
              <section key={key} className={`iv-day-cell${isToday ? ' today' : ''}`}>
                <header><span>{date.toLocaleDateString(undefined, { weekday: 'short' })}</span><strong>{date.getDate()}</strong></header>
                <div className="iv-day-events">
                  {items.map(eventCard)}
                  {items.length === 0 && <span className="muted iv-empty-day">No interviews</span>}
                </div>
              </section>
            )
          })}
        </div>
      )}

      <section className="card card-pad iv-history">
        <div className="eyebrow">Upcoming</div>
        {upcoming.length === 0 && <p className="muted">Nothing upcoming. Schedule an interview to get started.</p>}
        {upcoming.map((item) => (
          <button type="button" key={item.id} className="iv-history-row" onClick={() => setSelected(item)}>
            <Avatar name={item.candidate_name || 'Candidate'} size={26} />
            <span><strong>{item.candidate_name || 'Candidate'}</strong><small className="muted">{formatDate(item.interview_date)} · {formatTime(item.start_time)}</small></span>
            <span className={`chip ${STATUS_CHIP[item.status] || 'chip-gray'}`}>{item.status}</span>
          </button>
        ))}
        <div className="eyebrow iv-history-title">History</div>
        {history.length === 0 && <p className="muted">No past interviews yet.</p>}
        {history.map((item) => (
          <button type="button" key={item.id} className="iv-history-row" onClick={() => setSelected(item)}>
            <Avatar name={item.candidate_name || 'Candidate'} size={26} />
            <span><strong>{item.candidate_name || 'Candidate'}</strong><small className="muted">{formatDate(item.interview_date)} · {formatTime(item.start_time)}</small></span>
            <span className={`chip ${STATUS_CHIP[item.status] || 'chip-gray'}`}>{item.status}</span>
          </button>
        ))}
      </section>

      {selected && (
        <div className="iv-modal-backdrop" onClick={() => setSelected(null)}>
          <section className="card card-pad iv-modal" onClick={(event) => event.stopPropagation()}>
            <div className="iv-modal-head">
              <h2>Interview details</h2>
              <button type="button" className="icon-btn" onClick={() => setSelected(null)} aria-label="Close"><NwIcon name="x" /></button>
            </div>
            <p><strong>Candidate:</strong> {selected.candidate_name || 'Candidate'} {selected.candidate_email ? `(${selected.candidate_email})` : ''}</p>
            <p><strong>Title:</strong> {selected.title}</p>
            <p><strong>When:</strong> {formatDate(selected.interview_date)} · {formatTime(selected.start_time)} – {formatTime(selected.end_time || endOfSlot(selected.start_time, selected.duration_minutes))}</p>
            <p><strong>Type:</strong> {selected.interview_type === 'online' ? 'Online' : 'In-person'} · {selected.interview_type === 'online' ? selected.meeting_link : selected.location}</p>
            <p><strong>Status:</strong> {selected.status}</p>
            {selected.notes && <p><strong>Notes:</strong> {selected.notes}</p>}
            <div className="iv-form-actions">
              {selected.status === 'scheduled' && !isPastSlot(selected.interview_date, selected.start_time) && (
                <>
                  <button type="button" className="btn btn-secondary" onClick={() => openReschedule(selected)}>Reschedule</button>
                  <button type="button" className="btn btn-danger" disabled={busy} onClick={() => cancelInterview(selected)}>Cancel interview</button>
                </>
              )}
              <button type="button" className="btn btn-primary" onClick={() => setSelected(null)}>Close</button>
            </div>
          </section>
        </div>
      )}

      {rescheduling && (
        <div className="iv-modal-backdrop" onClick={() => setRescheduling(null)}>
          <section className="card card-pad iv-modal" onClick={(event) => event.stopPropagation()}>
            <div className="iv-modal-head">
              <h2>Reschedule interview</h2>
              <button type="button" className="icon-btn" onClick={() => setRescheduling(null)} aria-label="Close"><NwIcon name="x" /></button>
            </div>
            <p className="muted">{rescheduling.candidate_name || 'Candidate'} · {localTimeZone()}</p>
            <label className="iv-field">
              <span>New date</span>
              <input className="input" type="date" min={todayString()} value={resDate} onChange={(event) => { setResDate(event.target.value); setResTime('') }} />
            </label>
            <div className="iv-slot-grid">
              {rescheduleSlots.map((slot) => {
                const past = isPastSlot(resDate, slot)
                const booked = resBooked.includes(slot)
                return (
                  <button key={slot} type="button" className={`iv-slot${resTime === slot ? ' active' : ''}`} disabled={past || booked} title={past ? 'Past' : booked ? 'Booked' : formatTime(slot)} onClick={() => setResTime(slot)}>
                    {formatTime(slot)}{past && <small>Past</small>}{booked && <small>Booked</small>}
                  </button>
                )
              })}
            </div>
            <div className="iv-form-actions">
              <button type="button" className="btn btn-primary" disabled={!resTime || busy} onClick={confirmReschedule}>{busy ? 'Saving…' : 'Confirm new time'}</button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}









