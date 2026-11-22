// Local-time helpers for interview scheduling. All dates/times are interpreted
// in the browser's configured timezone and sent to the backend together with
// the IANA timezone name so the server can validate the real current time.

export const SLOT_MINUTES = 30
export const DAY_START_HOUR = 9
export const DAY_END_HOUR = 18

export function localDateString(date = new Date()) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

export function todayString() {
  return localDateString(new Date())
}

export function addDays(dateString, days) {
  const [year, month, day] = String(dateString).split('-').map(Number)
  const date = new Date(year, month - 1, day)
  date.setDate(date.getDate() + days)
  return localDateString(date)
}

export function slotTimes(stepMinutes = SLOT_MINUTES) {
  const step = stepMinutes > 0 ? stepMinutes : SLOT_MINUTES
  const slots = []
  for (let minutes = DAY_START_HOUR * 60; minutes < DAY_END_HOUR * 60; minutes += step) {
    const hours = Math.floor(minutes / 60)
    const mins = minutes % 60
    slots.push(`${String(hours).padStart(2, '0')}:${String(mins).padStart(2, '0')}`)
  }
  return slots
}

export function localTimeZone() {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
  } catch {
    return 'UTC'
  }
}

export function isPastSlot(dateString, timeString) {
  if (!dateString || !timeString) return true
  const [year, month, day] = String(dateString).split('-').map(Number)
  const [hours, minutes] = String(timeString).split(':').map(Number)
  const slot = new Date(year, month - 1, day, hours, minutes, 0, 0)
  return slot.getTime() <= Date.now()
}

export function formatTime(timeString) {
  if (!timeString) return ''
  const [hours, minutes] = String(timeString).split(':').map(Number)
  const suffix = hours >= 12 ? 'PM' : 'AM'
  const display = hours % 12 || 12
  return `${display}:${String(minutes || 0).padStart(2, '0')} ${suffix}`
}

export function formatDate(dateString) {
  if (!dateString) return ''
  const [year, month, day] = String(dateString).split('-').map(Number)
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short', month: 'short', day: 'numeric', year: 'numeric',
  })
}

export function endOfSlot(timeString, minutes = SLOT_MINUTES) {
  if (!timeString) return ''
  const [hours, mins] = String(timeString).split(':').map(Number)
  const total = hours * 60 + mins + minutes
  return `${String(Math.floor(total / 60) % 24).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`
}
