import { useEffect, useMemo, useState } from 'react'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import { listCandidates } from '../services/candidates'
import { listJobs } from '../services/jobs'
import { draftCommunication } from '../services/rag'
import { ApiError } from '../services/api'

const emailTypes = ['Invite', 'Follow-up', 'Rejection']

const emailTones = ['Warm', 'Professional', 'Concise', 'Enthusiastic']

const EMAIL_TYPE_TO_DRAFT = {
  Invite: 'interview_invitation',
  'Follow-up': 'follow_up',
  Rejection: 'application_status',
}

const FOLDERS = [
  { key: 'drafts', label: 'Drafts' },
  { key: 'sent', label: 'Sent' },
  { key: 'scheduled', label: 'Scheduled' },
]

const TONE_NOTES = {
  Warm: 'Use a warm, appreciative tone.',
  Professional: 'Use a professional, respectful tone.',
  Concise: 'Keep the message very short and to the point.',
  Enthusiastic: 'Use an enthusiastic, energetic tone.',
}

function buildThread(candidate, job) {
  return {
    id: candidate.id,
    folder: 'drafts',
    name: candidate.full_name,
    email: candidate.email || '',
    role: job ? job.title : 'Your open role',
    match: null,
    type: 'Invite',
    tone: 'Warm',
    time: 'now',
    badges: ['AI draft'],
    listLine: 'Draft ready for review',
    candidateId: candidate.id,
  }
}

export default function MessagesPage() {
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [threads, setThreads] = useState([])
  const [drafts, setDrafts] = useState({})
  const [folder, setFolder] = useState('drafts')
  const [activeId, setActiveId] = useState(null)
  const [drafting, setDrafting] = useState(false)
  const [toast, setToast] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const [candidateRows, jobRows] = await Promise.all([listCandidates(), listJobs()])
        if (cancelled) return
        const job = jobRows.find((j) => j.status === 'open') || jobRows[0] || null
        const list = candidateRows.slice(0, 8).map((c) => buildThread(c, job))
        setThreads(list)
        setDrafts(Object.fromEntries(list.map((t) => [t.id, { type: t.type, tone: t.tone, subject: '', body: '', edits: 0, reviewed: false, ready: false }])))
        setActiveId(list[0]?.id ?? null)
        setLoadError('')
      } catch (err) {
        if (!cancelled) setLoadError(err instanceof ApiError ? err.message : 'Could not load messages.')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [])

  const thread = useMemo(() => threads.find((t) => t.id === activeId) || null, [threads, activeId])
  const draft = thread ? drafts[thread.id] || null : null
  const locked = thread ? thread.folder !== 'drafts' : false
  const counts = Object.fromEntries(FOLDERS.map((f) => [f.key, threads.filter((t) => t.folder === f.key).length]))

  useEffect(() => {
    if (!thread || locked) return undefined
    const current = drafts[thread.id]
    if (current && (current.ready || current.loading)) return undefined
    let cancelled = false
    setDrafting(true)
    setDrafts((d) => ({ ...d, [thread.id]: { ...d[thread.id], loading: true } }))
    draftCommunication({
      draft_type: EMAIL_TYPE_TO_DRAFT[current?.type || thread.type],
      candidate_id: thread.candidateId,
      custom_notes: TONE_NOTES[current?.tone || thread.tone],
    })
      .then((response) => {
        if (cancelled) return
        setDrafts((d) => ({
          ...d,
          [thread.id]: {
            ...d[thread.id],
            subject: response.draft.subject,
            body: response.draft.body,
            ready: true,
            loading: false,
          },
        }))
      })
      .catch((err) => {
        if (cancelled) return
        setDrafts((d) => ({
          ...d,
          [thread.id]: {
            ...d[thread.id],
            loading: false,
            error: err instanceof ApiError ? err.message : 'Could not generate the draft.',
          },
        }))
      })
      .finally(() => {
        if (!cancelled) setDrafting(false)
      })
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [thread && thread.id, locked])

  function flash(message) {
    setToast(message)
    window.setTimeout(() => setToast(''), 2400)
  }

  function patchDraft(patch) {
    if (!thread) return
    setDrafts((d) => ({ ...d, [thread.id]: { ...d[thread.id], ...patch } }))
  }

  async function regenerate(next = {}) {
    if (!thread || locked || drafting) return
    const current = drafts[thread.id] || {}
    const type = next.type || current.type || thread.type
    const tone = next.tone || current.tone || thread.tone
    patchDraft({ type, tone, reviewed: false, error: '', loading: true })
    setDrafting(true)
    const notes = [TONE_NOTES[tone]]
    if (next.shorter) notes.push('Make the message noticeably shorter while keeping the key details.')
    if (next.details) notes.push('Include a line that the conversation will be on a video call and a calendar invite will follow once a time is confirmed.')
    try {
      const response = await draftCommunication({
        draft_type: EMAIL_TYPE_TO_DRAFT[type],
        candidate_id: thread.candidateId,
        custom_notes: notes.join(' '),
      })
      patchDraft({ subject: response.draft.subject, body: response.draft.body, ready: true, loading: false })
      if (!next.type && !next.tone) flash('Mitra rewrote the draft')
    } catch (err) {
      patchDraft({ loading: false, error: err instanceof ApiError ? err.message : 'Could not generate the draft.' })
    } finally {
      setDrafting(false)
    }
  }

  function finish(nextFolder, message, time, badge) {
    setThreads((list) => list.map((t) => (t.id === thread.id ? { ...t, folder: nextFolder, sent: true, time, badges: [badge], listLine: t.listLine } : t)))
    flash(message)
    const remaining = threads.filter((t) => t.folder === 'drafts' && t.id !== thread.id)
    if (remaining[0]) setActiveId(remaining[0].id)
  }

  function discard() {
    const remaining = threads.filter((t) => t.id !== thread.id)
    setThreads(remaining)
    flash('Draft discarded')
    const next = remaining.find((t) => t.folder === folder)
    if (next) setActiveId(next.id)
    else setActiveId(remaining[0]?.id ?? null)
  }

  const wordCount = draft && draft.body ? draft.body.trim().split(/\s+/).filter(Boolean).length : 0
  const canSend = draft && draft.ready && draft.reviewed && draft.body.trim() && draft.subject.trim()

  if (loading) {
    return <div className="page np"><div className="card cd-loading"><span className="spinner" aria-hidden="true" /> Loading messages…</div></div>
  }

  if (loadError) {
    return (
      <div className="page np">
        <header className="page-header">
          <div><div className="eyebrow">Communication</div><h1 className="page-title">Messages</h1></div>
        </header>
        <div className="card cd-error">
          <NwIcon name="x-circle" />
          <h2>Could not load messages</h2>
          <p className="muted">{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={() => window.location.reload()}>Try again</button>
        </div>
      </div>
    )
  }

  return (
    <div className="page np">
      <header className="page-header">
        <div>
          <div className="eyebrow">Communication</div>
          <h1 className="page-title">Messages</h1>
          <p className="page-sub">Mitra drafts thoughtful emails. You review, tweak and send — nothing goes out without you.</p>
        </div>
      </header>

      <div className="ms-layout">
        <section className="card ms-list" aria-label="Messages">
          <div className="ms-tabs" role="tablist">
            {FOLDERS.map((f) => (
              <button
                key={f.key}
                type="button"
                role="tab"
                aria-selected={folder === f.key}
                className={folder === f.key ? 'active' : ''}
                onClick={() => {
                  setFolder(f.key)
                  const first = threads.find((t) => t.folder === f.key)
                  if (first) setActiveId(first.id)
                }}
              >
                {f.label} · {counts[f.key]}
              </button>
            ))}
          </div>
          <ul>
            {threads.filter((t) => t.folder === folder).map((t) => (
              <li key={t.id}>
                <button type="button" className={`ms-item ${thread && t.id === thread.id ? 'active' : ''}`} onClick={() => setActiveId(t.id)}>
                  <Avatar name={t.name} size={34} />
                  <span className="ms-item-text">
                    <span className="ms-item-top">
                      <strong>{t.name}</strong>
                      <small className="muted">{t.time}</small>
                    </span>
                    <span className="muted ms-line">{t.listLine}</span>
                    <span className="ms-badges">
                      {t.badges.map((b) => (
                        <span key={b} className={`chip ${b === 'Needs review' ? 'chip-amber' : b === 'Replied' ? 'chip-green' : b === 'Scheduled' ? 'chip-coral' : 'chip-indigo'}`}>
                          {b === 'AI draft' && <NwIcon name="sparkle" />} {b}
                        </span>
                      ))}
                    </span>
                  </span>
                </button>
              </li>
            ))}
            {threads.filter((t) => t.folder === folder).length === 0 && <li className="ms-empty muted">Nothing here yet.</li>}
          </ul>
        </section>

        {thread && draft ? (
          <section className="card ms-editor" aria-label="Email editor">
            <div className="ms-to">
              <span className="muted">To</span>
              <span className="ms-recipient">
                <Avatar name={thread.name} size={22} />
                <strong>{thread.name}</strong>
                {thread.email && <span className="muted">&lt;{thread.email}&gt;</span>}
              </span>
              <span className="muted ms-job"><NwIcon name="briefcase" /> {thread.role}</span>
            </div>

            {!locked && (
              <div className="ms-options">
                <div>
                  <div className="eyebrow">Email type</div>
                  <div className="seg ms-seg" role="group" aria-label="Email type">
                    {emailTypes.map((t) => (
                      <button key={t} type="button" disabled={draft.loading} className={draft.type === t ? 'active' : ''} aria-pressed={draft.type === t} onClick={() => regenerate({ type: t })}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="eyebrow">Tone</div>
                  <div className="ms-tones" role="group" aria-label="Tone">
                    {emailTones.map((t) => (
                      <button key={t} type="button" disabled={draft.loading} className={draft.tone === t ? 'active' : ''} aria-pressed={draft.tone === t} onClick={() => regenerate({ tone: t })}>
                        {t}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="field">
              <label className="eyebrow" htmlFor="ms-subject">Subject</label>
              <input id="ms-subject" className="input" value={draft.subject} readOnly={locked} onChange={(e) => patchDraft({ subject: e.target.value, reviewed: false })} />
            </div>

            <div className="ms-body">
              <div className="ms-body-bar">
                <span className="ai-badge"><NwIcon name="sparkle" /> Drafted by Mitra · {draft.tone}</span>
                {!locked && (
                  <span className="ms-ai-actions">
                    <button type="button" className="link" disabled={draft.loading} onClick={() => regenerate()}><NwIcon name="refresh" /> Regenerate</button>
                    <button type="button" className="link" disabled={draft.loading} onClick={() => regenerate({ shorter: true })}>Shorter</button>
                    <button type="button" className="link" disabled={draft.loading} onClick={() => regenerate({ details: true })}>Add details</button>
                  </span>
                )}
              </div>
              {draft.loading ? (
                <p className="ms-drafting" style={{ padding: 16 }}>
                  <NwIcon name="sparkle" /> Mitra is writing a {draft.tone.toLowerCase()} {draft.type.toLowerCase()}…
                </p>
              ) : (
                <>
                  <label className="sr-only" htmlFor="ms-text">Email body</label>
                  <textarea
                    id="ms-text"
                    className="textarea ms-text"
                    rows={12}
                    value={draft.body}
                    readOnly={locked}
                    onChange={(e) => patchDraft({ body: e.target.value, reviewed: false })}
                  />
                </>
              )}
              <div className="ms-body-foot">
                {draft.type === 'Invite'
                  ? (
                    <span className="ms-tokens">
                      <code>Send slots from the Interviews page</code>
                    </span>
                  )
                  : <span />}
                <span className="muted">{wordCount} words · {draft.edits ? 'Edited by you' : 'As drafted'}{draft.edits ? ` · ${draft.edits} change${draft.edits === 1 ? '' : 's'}` : ''}</span>
              </div>
            </div>

            {draft.error && (
              <p className="ms-locked"><NwIcon name="x-circle" style={{ color: 'var(--danger)' }} /> {draft.error}{' '}
                <button type="button" className="link" onClick={() => regenerate()}>Retry</button>
              </p>
            )}

            {locked ? (
              <p className="ms-locked muted"><NwIcon name="check-circle" /> This message was {thread.folder === 'sent' ? 'sent' : 'scheduled'} and can no longer be edited.</p>
            ) : (
              <>
                <section className="ms-review" aria-label="Review before sending">
                  <span className="ms-review-icon"><NwIcon name="shield" /></span>
                  <div>
                    <h2>Review before sending</h2>
                    <label className="ms-confirm">
                      <input type="checkbox" checked={draft.reviewed} onChange={(e) => patchDraft({ reviewed: e.target.checked })} />
                      I’ve reviewed this draft and it’s ready to send
                    </label>
                  </div>
                </section>

                <p className="ms-demo-note">
                  <NwIcon name="shield" /> Email delivery isn’t connected to this app. Send and Schedule only move the draft between folders as a demo.
                </p>
                <div className="ms-send">
                  <button type="button" className="btn btn-ghost" onClick={discard}>Discard</button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={!canSend}
                    onClick={() => finish('scheduled', `Demo only: draft moved to Scheduled — no email will be sent`, 'Tomorrow 9:00', 'Scheduled (demo)')}
                  >
                    <NwIcon name="clock" /> Schedule send (demo)
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={!canSend}
                    onClick={() => finish('sent', `Demo only: draft moved to Sent — no email was delivered`, 'Just now', 'Sent (demo)')}
                  >
                    <NwIcon name="send" /> Send (demo)
                  </button>
                </div>
              </>
            )}
          </section>
        ) : (
          <section className="card ms-editor ms-none">
            <NwIcon name="mail" />
            <p className="muted">{threads.length === 0 ? 'Add candidates to start drafting messages.' : 'Select a message to review it.'}</p>
          </section>
        )}
      </div>

      {toast && (
        <div className="toast" role="status">
          <NwIcon name="check" /> {toast}
        </div>
      )}
    </div>
  )
}
