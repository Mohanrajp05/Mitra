import { useEffect, useState } from 'react'
import { listMyInterviews, acceptInterview, declineInterview, requestReschedule } from '../services/candidatePortal'

export default function CandidateInterviewsPage() {
  const [rows, setRows] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')

  useEffect(() => {
    let active = true
    listMyInterviews().then((r) => active && setRows(Array.isArray(r) ? r : [])).catch((e) => active && setError(e.message))
    return () => { active = false }
  }, [])

  async function act(id, fn) {
    setBusy(id); setError('')
    try { await fn(); const r = await listMyInterviews(); setRows(Array.isArray(r) ? r : []) }
    catch (e) { setError(e.message) }
    finally { setBusy('') }
  }

  return (
    <div className="page np" style={{ padding: 24 }}>
      <h1 className="page-title">My Interviews</h1>
      {error && <p style={{ color: 'var(--danger)' }}>{error}</p>}
      <div style={{ display: 'grid', gap: 12, marginTop: 16 }}>
        {rows.map((iv) => (
          <div key={iv.id} className="card card-pad">
            <h3>{iv.title}</h3>
            <p className="muted">{iv.interview_date} · {String(iv.start_time).slice(0,5)} – {String(iv.end_time).slice(0,5)} ({iv.time_zone})</p>
            <p><strong>Mode:</strong> {iv.interview_type}</p>
            {iv.meeting_link && <p><strong>Meeting link:</strong> <a href={iv.meeting_link}>{iv.meeting_link}</a></p>}
            {iv.location && <p><strong>Location:</strong> {iv.location}</p>}
            {iv.notes && <p><strong>Notes:</strong> {iv.notes}</p>}
            <p><strong>Response:</strong> {iv.candidate_response}</p>
            {iv.reschedule_status && <p><strong>Reschedule:</strong> {iv.reschedule_status}</p>}
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <button className="btn btn-secondary" disabled={busy === iv.id} onClick={() => act(iv.id, () => acceptInterview(iv.id))}>Accept</button>
              <button className="btn btn-secondary" disabled={busy === iv.id} onClick={() => act(iv.id, () => declineInterview(iv.id, 'Not available'))}>Decline</button>
              <button className="btn btn-secondary" disabled={busy === iv.id} onClick={() => act(iv.id, () => requestReschedule(iv.id, { suggested_date: iv.interview_date, suggested_start_time: iv.start_time, reason: 'Need different time' }))}>Request reschedule</button>
            </div>
          </div>
        ))}
        {rows.length === 0 && <p className="muted">No interviews scheduled.</p>}
      </div>
    </div>
  )
}
