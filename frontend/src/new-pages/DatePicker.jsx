import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import NwIcon from './NwIcon'
import { formatDate, localDateString, todayString } from './scheduling'

const WEEKDAYS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su']
const FALLBACK_WIDTH = 296
const FALLBACK_HEIGHT = 340
const EDGE_GAP = 8

function parseDate(value) {
  if (!value) return new Date()
  const [year, month, day] = String(value).split('-').map(Number)
  if (!year || !month || !day) return new Date()
  return new Date(year, month - 1, day)
}

function gridFor(monthDate, minDate) {
  const year = monthDate.getFullYear()
  const month = monthDate.getMonth()
  const first = new Date(year, month, 1)
  const offset = (first.getDay() + 6) % 7
  const start = new Date(year, month, 1 - offset)
  const today = todayString()
  return Array.from({ length: 42 }, (_, index) => {
    const date = new Date(start)
    date.setDate(start.getDate() + index)
    const key = localDateString(date)
    return {
      key,
      day: date.getDate(),
      outside: date.getMonth() !== month,
      disabled: Boolean(minDate && key < minDate),
      today: key === today,
    }
  })
}

export default function DatePicker({ id, value, min, onChange }) {
  const [open, setOpen] = useState(false)
  const [view, setView] = useState(() => {
    const date = parseDate(value || min)
    return new Date(date.getFullYear(), date.getMonth(), 1)
  })
  const [position, setPosition] = useState({ top: 0, left: 0, placement: 'below' })
  const rootRef = useRef(null)
  const iconRef = useRef(null)
  const popupRef = useRef(null)
  const minDate = min || todayString()

  useLayoutEffect(() => {
    if (!open) return undefined
    const place = () => {
      // Anchor to the actual calendar icon button, not the whole field.
      const icon = iconRef.current?.getBoundingClientRect()
      if (!icon) return
      const popup = popupRef.current
      const width = popup?.offsetWidth || FALLBACK_WIDTH
      const height = popup?.offsetHeight || FALLBACK_HEIGHT

      let top = icon.bottom + 6
      let placement = 'below'
      if (top + height > window.innerHeight - EDGE_GAP) {
        const above = icon.top - height - 6
        if (above >= EDGE_GAP) {
          top = above
          placement = 'above'
        } else {
          // Neither side fits fully: stay below and keep the popup in view.
          top = Math.max(EDGE_GAP, window.innerHeight - height - EDGE_GAP)
        }
      }
      top = Math.max(EDGE_GAP, Math.min(top, window.innerHeight - height - EDGE_GAP))
      // Right-align the popup with the calendar icon's right edge.
      const left = Math.max(
        EDGE_GAP,
        Math.min(icon.right - width, window.innerWidth - width - EDGE_GAP),
      )
      setPosition({ top, left, placement })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, true)
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place, true)
    }
  }, [open, view])

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (
        !rootRef.current?.contains(event.target)
        && !popupRef.current?.contains(event.target)
      ) {
        setOpen(false)
      }
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const days = useMemo(() => gridFor(view, minDate), [view, minDate])
  const monthLabel = view.toLocaleDateString(undefined, {
    month: 'long',
    year: 'numeric',
  })
  const portalTarget = document.querySelector('.np') || document.body

  function shiftMonth(direction) {
    setView((current) => new Date(current.getFullYear(), current.getMonth() + direction, 1))
  }

  function chooseDay(date) {
    if (date.disabled) return
    onChange(date.key)
    setOpen(false)
  }

  return (
    <>
      <div
        id={id}
        ref={rootRef}
        className="input dp-trigger"
      >
        <button
          type="button"
          className="dp-value"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <span>{value ? formatDate(value) : 'Select date'}</span>
        </button>
        <button
          type="button"
          ref={iconRef}
          className="dp-calendar"
          aria-label="Choose date"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => setOpen((current) => !current)}
        >
          <NwIcon name="calendar-outline" size={20} />
        </button>
      </div>

      {open
        && createPortal(
          <div
            ref={popupRef}
            className="np dp-popover"
            role="dialog"
            aria-label="Choose interview date"
            data-placement={position.placement}
            style={{
              position: 'fixed',
              top: position.top,
              left: position.left,
              zIndex: 1200,
            }}
          >
            <div className="dp-head">
              <button
                type="button"
                className="dp-nav"
                aria-label="Previous month"
                onClick={() => shiftMonth(-1)}
              >
                <NwIcon name="chevron-left" size={16} />
              </button>
              <strong>{monthLabel}</strong>
              <button
                type="button"
                className="dp-nav"
                aria-label="Next month"
                onClick={() => shiftMonth(1)}
              >
                <NwIcon name="chevron-right" size={16} />
              </button>
            </div>
            <div className="dp-weekdays">
              {WEEKDAYS.map((day) => <span key={day}>{day}</span>)}
            </div>
            <div className="dp-days">
              {days.map((date) => (
                <button
                  key={date.key}
                  type="button"
                  className={`dp-day${date.key === value ? ' selected' : ''}${date.today ? ' today' : ''}${date.outside ? ' outside' : ''}`}
                  disabled={date.disabled}
                  aria-label={date.key}
                  onClick={() => chooseDay(date)}
                >
                  {date.day}
                </button>
              ))}
            </div>
          </div>,
          portalTarget,
        )}
    </>
  )
}
