export const calendarStart = 9
export const calendarEnd = 18
export const HOUR_PX = 56

export const weekDays = [
  { key: 'mon', label: 'Mon' },
  { key: 'tue', label: 'Tue' },
  { key: 'wed', label: 'Wed' },
  { key: 'thu', label: 'Thu' },
  { key: 'fri', label: 'Fri' },
]

function thisMondayUtc() {
  const now = new Date()
  const day = (now.getUTCDay() + 6) % 7
  const monday = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()) - day * 86400000
  return monday
}

export function weekDates(offset) {
  const monday = thisMondayUtc() + offset * 7 * 86400000
  return weekDays.map((d, i) => new Date(monday + i * 86400000))
}

export function rangeLabel(dates) {
  const first = dates[0]
  const last = dates[dates.length - 1]
  const month = last.toLocaleString('en-GB', { month: 'long', timeZone: 'UTC' })
  const firstMonth = first.toLocaleString('en-GB', { month: 'long', timeZone: 'UTC' })
  const head = firstMonth === month ? `${first.getUTCDate()}` : `${first.getUTCDate()} ${firstMonth.slice(0, 3)}`
  return `${head} – ${last.getUTCDate()} ${month} ${last.getUTCFullYear()}`
}

export function todayDayIndex() {
  const now = new Date()
  return (now.getUTCDay() + 6) % 7
}

export function nowHoursUtc() {
  const now = new Date()
  return now.getUTCHours() + now.getUTCMinutes() / 60
}
