import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NwIcon from './NwIcon'
import DatePicker from './DatePicker'
import Avatar from './Avatar'
import { listCandidates } from '../services/candidates'
import {
  createScheduledInterview,
  getInterviewAvailability,
} from '../services/scheduling'
import { ApiError } from '../services/api'
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

function candidateRole(candidate) {
  const profile = candidate.extracted_profile
  return (
    profile?.job_title ||
    profile?.role ||
    (Array.isArray(candidate.skills) && candidate.skills.length > 0
      ? candidate.skills.slice(0, 3).join(', ')
      : '') ||
    'Candidate'
  )
}

export default function ScheduleInterviewPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState('candidate')
  const [candidates, setCandidates] = useState([])
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const [title, setTitle] = useState('')
  const [interviewDate, setInterviewDate] = useState(todayString())
  const [duration, setDuration] = useState(SLOT_MINUTES)
  const [startTime, setStartTime] = useState('')
  const [interviewType, setInterviewType] = useState('online')
  const [meetingLink, setMeetingLink] = useState('')
  const [location, setLocation] = useState('')
  const [notes, setNotes] = useState('')
  const [bookedSlots, setBookedSlots] = useState([])
  const [availabilityLoading, setAvailabilityLoading] = useState(false)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const rows = await listCandidates()
        if (active) setCandidates(Array.isArray(rows) ? rows : [])
      } catch (err) {
        if (active) setError(err instanceof ApiError ? err.message : 'Could not load candidates.')
      } finally {
        if (active) setLoading(false)
      }
    }
    load()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (step !== 'form' || !selected || !interviewDate) return
    let active = true
    setAvailabilityLoading(true)
    getInterviewAvailability(selected.id, interviewDate)
      .then((result) => {
        if (active) setBookedSlots(Array.isArray(result?.booked_slots) ? result.booked_slots : [])
      })
      .catch((err) => {
        if (active) setError(err instanceof ApiError ? err.message : 'Could not check booked slots.')
      })
      .finally(() => { if (active) setAvailabilityLoading(false) })
    return () => { active = false }
  }, [step, selected?.id, interviewDate])

  useEffect(() => {
    if (interviewDate && startTime && isPastSlot(interviewDate, startTime)) {
      setStartTime('')
    }
  }, [interviewDate, startTime])

  const slots = useMemo(() => slotTimes(duration), [duration])
  const slotButtons = useMemo(
    () =>
      slots.map((slot) => ({
        slot,
        past: isPastSlot(interviewDate, slot),
        booked: bookedSlots.includes(slot),
      })),
    [interviewDate, bookedSlots, slots],
  )

  function chooseCandidate(candidate) {
    setSelected(candidate)
    setTitle(`Interview with ${candidate.full_name || 'candidate'}`)
    setInterviewDate(todayString())
    setStartTime('')
    setError('')
    setStep('form')
  }

  const valid =
    Boolean(selected) &&
    Boolean(title.trim()) &&
    Boolean(interviewDate) &&
    Boolean(startTime) &&
    !isPastSlot(interviewDate, startTime) &&
    !bookedSlots.includes(startTime) &&
    (interviewType === 'online' ? Boolean(meetingLink.trim()) : Boolean(location.trim()))

  async function confirm() {
    if (!valid || submitting) return
    setSubmitting(true)
    setError('')
    try {
      await createScheduledInterview({
        candidate_id: selected.id,
        title: title.trim(),
        interview_date: interviewDate,
        start_time: startTime,
        time_zone: localTimeZone(),
        duration_minutes: duration,
        interview_type: interviewType,
        meeting_link: interviewType === 'online' ? meetingLink.trim() : null,
        location: interviewType === 'in_person' ? location.trim() : null,
        notes: notes.trim() || null,
      })
      navigate('/interviews', { state: { notice: 'Interview scheduled successfully.' } })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not schedule the interview.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Scheduling</div>
          <h1 className="page-title">{step === 'candidate' ? 'Select a candidate' : 'Schedule interview'}</h1>
          <p className="page-sub">
            {step === 'candidate'
              ? 'Choose the candidate you want to interview.'
              : 'Pick a real future date and an available 30-minute slot.'}
          </p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={() => (step === 'form' ? setStep('candidate') : navigate('/interviews'))}>
            <NwIcon name="chevron-left" /> Back
          </button>
        </div>
      </header>

      {error && <p className="as-note" style={{ color: 'var(--danger)' }}>{error}</p>}

      {step === 'candidate' ? (
        <section className="card card-pad">
          {loading && <p className="muted">Loading candidates…</p>}
          {!loading && candidates.length === 0 && <p className="muted">No candidates yet. Create a candidate first.</p>}
          <div className="iv-candidates">
            {candidates.map((candidate) => (
              <button
                type="button"
                key={candidate.id}
                className={`iv-candidate${selected?.id === candidate.id ? ' active' : ''}`}
                onClick={() => setSelected(candidate)}
              >
                <Avatar name={candidate.full_name || 'Candidate'} size={36} />
                <span className="iv-candidate-main">
                  <strong>{candidate.full_name || 'Unnamed candidate'}</strong>
                  <small className="muted">{candidate.email || 'No email'} · {candidateRole(candidate)}</small>
                  {candidate.experience_years != null && <small className="muted">{candidate.experience_years} years experience</small>}
                </span>
              </button>
            ))}
          </div>
          <div className="iv-form-actions">
            <button
              type="button"
              className="btn btn-primary"
              disabled={!selected}
              onClick={() => selected && chooseCandidate(selected)}
            >
              Continue <NwIcon name="chevron-right" />
            </button>
          </div>
        </section>
      ) : (
        <div className="iv-schedule-layout">
          <section className="card card-pad">
            <div className="eyebrow">Candidate</div>
            <div className="iv-selected">
              <Avatar name={selected?.full_name || 'Candidate'} size={40} />
              <div>
                <strong>{selected?.full_name || 'Candidate'}</strong>
                <p className="muted">{selected?.email || 'No email'} · {candidateRole(selected)}</p>
                {selected?.phone && <p className="muted">{selected.phone}</p>}
              </div>
            </div>

            <div className="iv-form-grid">
              <label className="iv-field">
                <span>Interview title / role</span>
                <input className="input" value={title} onChange={(event) => setTitle(event.target.value)} />
              </label>
              <label className="iv-field">
                <span>Date</span>
                <DatePicker
                  id="iv-interview-date"
                  value={interviewDate}
                  min={todayString()}
                  onChange={(date) => {
                    setInterviewDate(date)
                    setStartTime('')
                  }}
                />
              </label>
              <fieldset className="iv-field iv-type">
                <legend>Duration</legend>
                {[10, 30].map((minutes) => (
                  <label key={minutes}>
                    <input
                      type="radio"
                      name="interview-duration"
                      checked={duration === minutes}
                      onChange={() => {
                        setDuration(minutes)
                        setStartTime('')
                      }}
                    />
                    {minutes} minutes
                  </label>
                ))}
              </fieldset>
              <fieldset className="iv-field iv-type">
                <legend>Interview type</legend>
                <label><input type="radio" name="interview-type" checked={interviewType === 'online'} onChange={() => setInterviewType('online')} /> Online</label>
                <label><input type="radio" name="interview-type" checked={interviewType === 'in_person'} onChange={() => setInterviewType('in_person')} /> In-person</label>
              </fieldset>
              {interviewType === 'online' ? (
                <label className="iv-field">
                  <span>Meeting link</span>
                  <input className="input" type="url" placeholder="https://meet.example.com/..." value={meetingLink} onChange={(event) => setMeetingLink(event.target.value)} />
                </label>
              ) : (
                <label className="iv-field">
                  <span>Location</span>
                  <input className="input" placeholder="Office / address" value={location} onChange={(event) => setLocation(event.target.value)} />
                </label>
              )}
              <label className="iv-field iv-notes">
                <span>Notes (optional)</span>
                <textarea className="input" rows={3} value={notes} onChange={(event) => setNotes(event.target.value)} />
              </label>
            </div>
          </section>

          <section className="card card-pad">
            <div className="iv-slot-head">
              <div className="eyebrow">Available {duration}-minute slots</div>
              <p className="muted">{formatDate(interviewDate)} · times shown in {localTimeZone()}</p>
            </div>
            {availabilityLoading && <p className="muted">Checking availability…</p>}
            <div className="iv-slot-grid" role="radiogroup" aria-label="Start time">
              {slotButtons.map(({ slot, past, booked }) => (
                <button
                  key={slot}
                  type="button"
                  role="radio"
                  aria-checked={startTime === slot}
                  className={`iv-slot${startTime === slot ? ' active' : ''}`}
                  disabled={past || booked}
                  title={past ? 'This time has already passed' : booked ? 'Already booked' : `${formatTime(slot)} – ${formatTime(endOfSlot(slot, duration))}`}
                  onClick={() => setStartTime(slot)}
                >
                  {formatTime(slot)}
                  {past && <small>Past</small>}
                  {booked && <small>Booked</small>}
                </button>
              ))}
            </div>
            <p className="muted iv-slot-help">
              Past times and already-booked slots are disabled. The backend re-checks the time and conflicts before saving.
            </p>
            <div className="iv-form-actions">
              <button type="button" className="btn btn-primary" disabled={!valid || submitting} onClick={confirm}>
                {submitting ? 'Scheduling…' : 'Confirm Schedule'}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  )
}
