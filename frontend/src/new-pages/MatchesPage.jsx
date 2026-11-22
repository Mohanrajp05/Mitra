import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import NwIcon from './NwIcon'
import Avatar from './Avatar'
import ScoreRing, { scoreColor } from './ScoreRing'
import JobSearch from '../components/JobSearch'
import { listCandidates } from '../services/candidates'
import { listJobs } from '../services/jobs'
import { draftCommunication, listDocuments, matchCandidate } from '../services/rag'
import { ApiError } from '../services/api'
import {
  getInflightMatch,
  getMatchEntry,
  getMatchPageData,
  getMatchViewState,
  setInflightMatch,
  setMatchEntry,
  setMatchPageData,
  setMatchViewState,
} from '../services/matchCache'

const CONCURRENCY = 2

const DRAFT_TYPES = [
  { value: 'interview_invitation', label: 'Interview invitation' },
  { value: 'follow_up', label: 'Follow-up' },
  { value: 'application_status', label: 'Application status' },
]

const STATUS_META = {
  matched: { icon: 'check-circle', label: 'Matched' },
  partial: { icon: 'half-circle', label: 'Partial' },
  missing: { icon: 'x-circle', label: 'Missing' },
}

function signature(job, candidate) {
  return [
    job.id,
    job.updated_at || '',
    (job.required_skills || []).join('|'),
    candidate.id,
    candidate.updated_at || '',
    (candidate.skills || []).join('|'),
    candidate.resume_text || '',
  ].join('::')
}

function lowerSet(list) {
  return new Set((list || []).map((value) => String(value).toLowerCase()))
}

function normalizeDecision(value) {
  if (value === 'rejected') return 'not_shortlisted'
  return value || null
}

function readMatchResponse(response, candidateId, jobId) {
  const result = response?.match
  if (response?.candidate_id !== candidateId || response?.job_id !== jobId) {
    throw new ApiError('The matching API returned a result for a different job or candidate. Please retry.', 502)
  }
  const score = result?.match_score ?? (typeof result?.relevance_score === 'number' ? result.relevance_score * 100 : null)
  if (!result || typeof result !== 'object' || typeof score !== 'number') {
    throw new ApiError('The matching API returned an invalid score response. Please retry.', 502)
  }
  if (score < 0 || score > 100) {
    throw new ApiError('The matching API returned an out-of-range score. Please retry.', 502)
  }
  if (!Array.isArray(result.matched_skills) || !Array.isArray(result.partial_skills || result.unverified_skills) || !Array.isArray(result.missing_skills) || !Array.isArray(result.evidence)) {
    throw new ApiError('The matching API returned an incomplete comparison. Please retry.', 502)
  }
  return result
}

function findEvidence(match, skill) {
  const needle = skill.toLowerCase()
  return (match.evidence || []).find((item) => item.quote.toLowerCase().includes(needle)) || null
}

function buildRows(job, candidate, match) {
  const matched = lowerSet(match.matched_skills)
  const unverified = lowerSet(match.unverified_skills)
  const candidateSkills = lowerSet(candidate.skills)
  const rows = (job.required_skills || []).map((skill) => {
    const key = skill.toLowerCase()
    let status = 'missing'
    if (matched.has(key)) status = 'matched'
    else if (unverified.has(key)) status = 'partial'
    let evidenceText
    let source = ''
    if (status === 'matched') {
      const evidence = findEvidence(match, skill)
      if (evidence) {
        evidenceText = evidence.quote
        source = evidence.source
      } else if (candidateSkills.has(key)) {
        evidenceText = 'Listed in the candidate profile'
      } else {
        evidenceText = 'Verified by the backend match; no resume quote was returned'
      }
    } else if (status === 'partial') {
      evidenceText = candidateSkills.has(key)
        ? 'Listed in the candidate profile, but not verified against the resume'
        : 'Not verified against the resume text; no supporting quote was returned'
    } else {
      evidenceText = 'Not found in the parsed resume'
    }
    return {
      key: `skill-${key}`,
      label: skill,
      note: 'Required skill',
      jobReq: 'Required',
      evidenceText,
      source,
      status,
      statusLabel: STATUS_META[status].label,
    }
  })

  const required = job.experience_required
  if (required !== null && required !== undefined) {
    const years = typeof candidate.experience_years === 'number' ? candidate.experience_years : null
    let status = 'partial'
    let evidenceText = 'Years of experience are not available'
    if (years !== null) {
      status = years >= required ? 'matched' : 'missing'
      evidenceText = `${years} year${years === 1 ? '' : 's'} on the candidate profile`
    }
    rows.push({
      key: 'experience',
      label: 'Experience',
      note: 'Total experience',
      jobReq: `${required}+ years`,
      evidenceText,
      source: '',
      status,
      statusLabel: status === 'matched' ? 'Meets' : status === 'missing' ? 'Not met' : 'Unknown',
    })
  }

  return rows
}

function resumeInfo(candidate, resumeDocs, docsState) {
  const doc = resumeDocs.get(candidate.id) || null
  const parsed = Boolean(candidate.resume_text && candidate.resume_text.trim())
  const available = parsed || Boolean(doc)
  let label = 'No resume uploaded'
  if (parsed) label = 'Parsed resume on file'
  else if (doc) label = 'Resume uploaded, text not parsed'
  else if (docsState !== 'ready') label = 'Resume status unavailable'
  return { available, parsed, doc, label }
}

function CandidateScore({ entry }) {
  if (entry.status === 'ready') return <ScoreRing score={entry.score} size={32} stroke={3} />
  if (entry.status === 'loading') return <span className="mt-spinner-xs" aria-label="Scoring" />
  if (entry.status === 'error') return <span className="mt-cand-flag" title={entry.error}>!</span>
  if (entry.status === 'blocked') return <span className="mt-cand-flag wait" title={entry.error}>N/A</span>
  return <span className="mt-cand-flag wait" aria-label="Queued">…</span>
}

function cacheStatusLabel(entry) {
  if (!entry || entry.status !== 'ready') return ''
  if (entry.cacheStatus === 'hit') return 'Cached result'
  if (entry.cacheStatus === 'refresh') return 'Recalculated'
  return 'Updated'
}

function readyEntryFromCache(cached) {
  if (!cached || cached.status !== 'ready') return null
  return {
    status: 'ready',
    score: cached.score,
    match: cached.match,
    cacheStatus: cached.cacheStatus || 'hit',
  }
}

export default function MatchesPage() {
  const navigate = useNavigate()
  const savedView = getMatchViewState()
  const cachedData = getMatchPageData()
  const hasCachedData = Array.isArray(cachedData.jobs) && Array.isArray(cachedData.candidates)
  const [loading, setLoading] = useState(!hasCachedData)
  const [refreshing, setRefreshing] = useState(false)
  const [loadError, setLoadError] = useState('')
  const [docsState, setDocsState] = useState(hasCachedData ? (cachedData.docsState || 'ready') : 'loading')
  const [jobs, setJobs] = useState(hasCachedData ? cachedData.jobs : [])
  const [candidates, setCandidates] = useState(hasCachedData ? cachedData.candidates : [])
  const [documents, setDocuments] = useState(hasCachedData ? (cachedData.documents || []) : [])
  const resolvedInitialJobId = (() => {
    if (!hasCachedData) return savedView.jobId
    const keep = (cachedData.jobs || []).some((row) => row.id === savedView.jobId)
      ? savedView.jobId
      : (cachedData.jobs?.[0]?.id ?? null)
    return keep
  })()
  const resolvedInitialActiveId = (() => {
    if (!hasCachedData) return savedView.activeId
    const keep = (cachedData.candidates || []).some((row) => row.id === savedView.activeId)
      ? savedView.activeId
      : (cachedData.candidates?.[0]?.id ?? null)
    return keep
  })()
  const [jobId, setJobId] = useState(resolvedInitialJobId)
  const [activeId, setActiveId] = useState(resolvedInitialActiveId)
  const [rank, setRank] = useState(() => {
    if (!hasCachedData) return {}
    const j = (cachedData.jobs || []).find((row) => row.id === resolvedInitialJobId) || cachedData.jobs?.[0] || null
    if (!j) return {}
    const next = {}
    for (const candidate of cachedData.candidates || []) {
      const cacheKey = `${j.id}:${candidate.id}`
      const sig = signature(j, candidate)
      const cached = getMatchEntry(cacheKey)
      if (cached && cached.signature === sig && cached.status === 'ready') {
        next[candidate.id] = readyEntryFromCache(cached)
      } else if (cached && cached.signature === sig && cached.status === 'error') {
        next[candidate.id] = { status: 'error', error: cached.error || 'Match computation failed.' }
      } else if (cached && cached.signature === sig && cached.status === 'blocked') {
        next[candidate.id] = { status: 'blocked', error: cached.error || 'No resume is on file for this candidate.' }
      } else if (getInflightMatch(cacheKey)) {
        next[candidate.id] = { status: 'loading' }
      } else {
        next[candidate.id] = { status: 'pending' }
      }
    }
    return next
  })
  const [epoch, setEpoch] = useState(0)
  const [showWeights, setShowWeights] = useState(false)
  const [query, setQuery] = useState('')
  const [listFilter, setListFilter] = useState('all')
  const [decisions, setDecisions] = useState({}) // session-only, kept in component while mounted; decisions reset on full page refresh is acceptable per note in UI
  const [toast, setToast] = useState('')
  const [draftOpen, setDraftOpen] = useState(false)
  const [draftType, setDraftType] = useState('interview_invitation')
  const [draftNotes, setDraftNotes] = useState('')
  const [draftBusy, setDraftBusy] = useState(false)
  const [draftError, setDraftError] = useState('')
  const [draft, setDraft] = useState(null)
  const [copied, setCopied] = useState(false)

  const userPickedRef = useRef(Boolean(savedView.userPicked))
  const epochRef = useRef(0)
  const runKeyRef = useRef('')
  const initKeyRef = useRef('')
  const toastTimerRef = useRef(null)
  const mountedRef = useRef(true)

  const flash = useCallback((message) => {
    setToast(message)
    if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current)
    toastTimerRef.current = window.setTimeout(() => setToast(''), 2600)
  }, [])

  useEffect(() => {
    mountedRef.current = true
    return () => {
      mountedRef.current = false
      if (toastTimerRef.current) window.clearTimeout(toastTimerRef.current)
    }
  }, [])

  useEffect(() => {
    setMatchViewState({ jobId, activeId, userPicked: userPickedRef.current })
  }, [jobId, activeId])

  const loadData = useCallback(async ({ refresh = false, background = false } = {}) => {
    if (refresh) setRefreshing(true)
    else if (!background) setLoading(true)
    try {
      const [jobRows, candidateRows] = await Promise.all([listJobs(), listCandidates()])
      let docs = []
      let nextDocsState = 'ready'
      try {
        const response = await listDocuments()
        docs = response?.documents || []
      } catch {
        nextDocsState = 'error'
      }
      setJobs(jobRows)
      setCandidates(candidateRows)
      setDocuments(docs)
      setDocsState(nextDocsState)
      setMatchPageData({ jobs: jobRows, candidates: candidateRows, documents: docs, docsState: nextDocsState })
      setLoadError('')
      setJobId((prev) => {
        const keep = jobRows.some((job) => job.id === prev) ? prev : jobRows[0]?.id ?? null
        return keep
      })
      setActiveId((prev) => (candidateRows.some((candidate) => candidate.id === prev) ? prev : candidateRows[0]?.id ?? null))
      // Reloading data must not discard valid cached match results. Re-evaluate
      // signatures so unchanged results stay available and only changed/missing
      // ones are recomputed.
      setEpoch((value) => value + 1)
      if (refresh) flash('Data refreshed')
    } catch (err) {
      if (!background) {
        setLoadError(err instanceof ApiError ? err.message : 'Could not load jobs or candidates.')
      }
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [flash])

  useEffect(() => {
    loadData({ background: hasCachedData })
  }, [loadData, hasCachedData])

  const job = useMemo(() => jobs.find((row) => row.id === jobId) || null, [jobs, jobId])
  const active = useMemo(() => candidates.find((row) => row.id === activeId) || null, [candidates, activeId])

  const resumeDocs = useMemo(() => {
    const map = new Map()
    for (const doc of documents) {
      if (doc.source_type === 'resume' && doc.candidate_id) map.set(doc.candidate_id, doc)
    }
    return map
  }, [documents])

  const resumeIds = useMemo(() => {
    const ids = new Set()
    for (const candidate of candidates) {
      if ((candidate.resume_text && candidate.resume_text.trim()) || resumeDocs.has(candidate.id)) ids.add(candidate.id)
    }
    return ids
  }, [candidates, resumeDocs])

  epochRef.current = epoch
  runKeyRef.current = job ? `${job.id}:${epoch}` : ''

  useEffect(() => {
    const key = job ? `${job.id}:${epoch}` : ''
    if (initKeyRef.current === key) return
    initKeyRef.current = key
    if (!job) {
      setRank({})
      return
    }
    const next = {}
    for (const candidate of candidates) {
      const cacheKey = `${job.id}:${candidate.id}`
      const sig = signature(job, candidate)
      const cached = getMatchEntry(cacheKey)
      if (cached && cached.signature === sig && cached.status === 'ready') {
        next[candidate.id] = readyEntryFromCache(cached)
      } else if (cached && cached.signature === sig && cached.status === 'error') {
        next[candidate.id] = { status: 'error', error: cached.error || 'Match computation failed.' }
      } else if (cached && cached.signature === sig && cached.status === 'blocked') {
        next[candidate.id] = { status: 'blocked', error: cached.error || 'No resume is on file for this candidate.' }
      } else if (getInflightMatch(cacheKey)) {
        next[candidate.id] = { status: 'loading' }
      } else {
        next[candidate.id] = { status: 'pending' }
      }
    }
    setRank(next)
  }, [job, candidates, epoch])

  const applyEntry = useCallback((candidateId, runKey, entry, sig, cacheStatus) => {
    const key = job ? `${job.id}:${candidateId}` : ''
    if (entry.status === 'ready') {
      setMatchEntry(key, {
        signature: sig,
        status: 'ready',
        score: entry.score,
        match: entry.match,
        cacheStatus: cacheStatus || entry.cacheStatus || 'hit',
      })
    } else if (entry.status === 'error') {
      setMatchEntry(key, { signature: sig, status: 'error', error: entry.error })
    } else if (entry.status === 'blocked') {
      setMatchEntry(key, { signature: sig, status: 'blocked', error: entry.error })
    }
    if (mountedRef.current && runKey === runKeyRef.current) {
      setRank((prev) => ({ ...prev, [candidateId]: entry }))
    }
  }, [job])

  const startMatch = useCallback((jobRow, candidateRow, options = {}) => {
    const { forceRefresh = false } = options
    const key = `${jobRow.id}:${candidateRow.id}`
    const runKey = `${jobRow.id}:${epochRef.current}`
    const sig = signature(jobRow, candidateRow)

    if (docsState === 'ready' && !resumeIds.has(candidateRow.id)) {
      const blocked = { status: 'blocked', error: 'No resume is on file for this candidate.' }
      setMatchEntry(key, { signature: sig, ...blocked })
      if (runKey === runKeyRef.current) setRank((prev) => ({ ...prev, [candidateRow.id]: blocked }))
      return
    }

    // Reuse a valid completed result (unless an explicit recalculation is requested).
    if (!forceRefresh && docsState === 'ready') {
      const cached = getMatchEntry(key)
      if (cached && cached.signature === sig && cached.status === 'ready') {
        const ready = readyEntryFromCache(cached)
        if (ready && runKey === runKeyRef.current) {
          setRank((prev) => ({ ...prev, [candidateRow.id]: ready }))
        }
        return
      }
    }

    // Deduplicate: if the same request is already in flight, reuse it.
    const existing = getInflightMatch(key)
    if (existing) {
      if (runKey === runKeyRef.current) setRank((prev) => ({ ...prev, [candidateRow.id]: { status: 'loading' } }))
      existing
        .then((entry) => {
          if (!mountedRef.current) return
          if (runKey === runKeyRef.current) setRank((prev) => ({ ...prev, [candidateRow.id]: entry }))
          else if (entry.status === 'ready') {
            // Keep the result visible for the next view; nothing else to do.
          }
        })
        .catch(() => {
          if (mountedRef.current && runKey === runKeyRef.current) {
            setRank((prev) => {
              const current = prev[candidateRow.id]
              if (current && current.status === 'loading') return { ...prev, [candidateRow.id]: { status: 'pending' } }
              return prev
            })
          }
        })
      return
    }

    if (runKey === runKeyRef.current) setRank((prev) => ({ ...prev, [candidateRow.id]: { status: 'loading' } }))

    const promise = matchCandidate(candidateRow.id, jobRow.id, { forceRefresh })
      .then((response) => {
        const result = readMatchResponse(response, candidateRow.id, jobRow.id)
        const status = response?.cache_status || (response?.cached ? 'hit' : 'miss')
        const entry = {
          status: 'ready',
          score: Math.round(result.match_score ?? (result.relevance_score * 100)),
          match: result,
          cacheStatus: status,
        }
        setMatchEntry(key, { signature: sig, ...entry })
        return entry
      })
      .catch((err) => {
        const entry = {
          status: 'error',
          error: err instanceof ApiError ? err.message : 'Match computation failed.',
        }
        // Errors are not reusable as valid cached match results.
        setMatchEntry(key, { signature: sig, ...entry })
        throw entry
      })
      .finally(() => {
        setInflightMatch(key, null)
      })

    setInflightMatch(key, promise)
    promise
      .then((entry) => {
        if (mountedRef.current && runKey === runKeyRef.current) {
          setRank((prev) => ({ ...prev, [candidateRow.id]: entry }))
        }
      })
      .catch((entry) => {
        if (!mountedRef.current) return
        if (runKey === runKeyRef.current) {
          setRank((prev) => ({ ...prev, [candidateRow.id]: entry }))
        } else {
          setRank((prev) => (
            prev[candidateRow.id]?.status === 'loading'
              ? { ...prev, [candidateRow.id]: { status: 'pending' } }
              : prev
          ))
        }
      })
  }, [docsState, resumeIds])

  useEffect(() => {
    if (!job) return
    const running = candidates.filter((candidate) => Boolean(getInflightMatch(`${job.id}:${candidate.id}`))).length
    const capacity = CONCURRENCY - running
    if (capacity <= 0) return
    const pending = candidates.filter((candidate) => {
      const state = rank[candidate.id]?.status || 'pending'
      return state === 'pending' && !getInflightMatch(`${job.id}:${candidate.id}`)
    })
    pending.slice(0, capacity).forEach((candidate) => startMatch(job, candidate))
  }, [job, candidates, rank, epoch, startMatch])

  const retryCandidate = useCallback((candidateId, options = {}) => {
    if (!job) return
    const key = `${job.id}:${candidateId}`
    if (getInflightMatch(key)) return
    // Drop the stored error/blocked entry so the scheduler can re-run it.
    const existing = getMatchEntry(key)
    if (existing && (existing.status === 'error' || existing.status === 'blocked')) {
      setMatchEntry(key, null)
    }
    if (options.forceRefresh) setMatchEntry(key, null)
    setRank((prev) => ({ ...prev, [candidateId]: { status: 'pending' } }))
    // Force path is handled by startMatch reading the absence + force flag via
    // a microtask: mark pending now; the scheduler effect will pick it up, but
    // for explicit recalc we also trigger directly to bypass signature-hit reuse.
    if (options.forceRefresh) {
      const candidate = candidates.find((row) => row.id === candidateId)
      if (candidate) {
        // Defer so state is consistent; startMatch will see no valid cached ready entry.
        Promise.resolve().then(() => startMatch(job, candidate, { forceRefresh: true }))
      }
    }
  }, [job, candidates, startMatch])

  const retryFailed = useCallback(() => {
    if (!job) return
    setRank((prev) => {
      const next = { ...prev }
      for (const candidate of candidates) {
        const key = `${job.id}:${candidate.id}`
        if (next[candidate.id]?.status === 'error' && !getInflightMatch(key)) {
          setMatchEntry(key, null)
          next[candidate.id] = { status: 'pending' }
        }
      }
      return next
    })
  }, [job, candidates])

  const ranked = useMemo(() => {
    return candidates.map((candidate) => {
      const entry = rank[candidate.id] || { status: 'pending' }
      const info = resumeInfo(candidate, resumeDocs, docsState)
      const decision = jobId ? normalizeDecision(decisions[jobId]?.[candidate.id]) : null
      return { candidate, entry, info, decision }
    }).sort((a, b) => {
      const aScore = a.entry.status === 'ready' ? a.entry.score : -1
      const bScore = b.entry.status === 'ready' ? b.entry.score : -1
      if (bScore !== aScore) return bScore - aScore
      return a.candidate.full_name.localeCompare(b.candidate.full_name)
    })
  }, [candidates, rank, resumeDocs, docsState, decisions, jobId])

  const searchMatched = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return ranked
    return ranked.filter((row) => {
      const haystack = [
        row.candidate.full_name,
        row.candidate.email || '',
        ...(row.candidate.skills || []),
      ].join(' ').toLowerCase()
      return haystack.includes(needle)
    })
  }, [ranked, query])

  const filterCounts = useMemo(() => {
    let shortlisted = 0
    let notShortlisted = 0
    for (const row of searchMatched) {
      if (row.decision === 'shortlisted') shortlisted += 1
      else notShortlisted += 1
    }
    return {
      all: searchMatched.length,
      shortlisted,
      not_shortlisted: notShortlisted,
    }
  }, [searchMatched])

  const filtered = useMemo(() => {
    if (listFilter === 'shortlisted') {
      return searchMatched.filter((row) => row.decision === 'shortlisted')
    }
    if (listFilter === 'not_shortlisted') {
      return searchMatched.filter((row) => row.decision !== 'shortlisted')
    }
    return searchMatched
  }, [searchMatched, listFilter])

  const totals = useMemo(() => {
    let ready = 0
    let error = 0
    let blocked = 0
    let loadingCount = 0
    let pending = 0
    for (const candidate of candidates) {
      const status = rank[candidate.id]?.status || 'pending'
      if (status === 'ready') ready += 1
      else if (status === 'error') error += 1
      else if (status === 'blocked') blocked += 1
      else if (status === 'loading') loadingCount += 1
      else pending += 1
    }
    return { ready, error, blocked, loading: loadingCount, pending, total: candidates.length }
  }, [candidates, rank])

  useEffect(() => {
    if (userPickedRef.current) return
    const top = ranked.find((row) => row.entry.status === 'ready')
    const fallback = ranked.find((row) => row.info.available) || ranked[0] || null
    const target = top || fallback
    if (target && target.candidate.id !== activeId) setActiveId(target.candidate.id)
  }, [ranked, activeId])

  const activeRow = useMemo(() => ranked.find((row) => row.candidate.id === activeId) || null, [ranked, activeId])
  const activeEntry = activeRow?.entry || null
  const activeMatch = activeEntry?.status === 'ready' ? activeEntry.match : null
  const activeScore = activeEntry?.status === 'ready' ? activeEntry.score : null
  const activeDecision = jobId && activeId ? normalizeDecision(decisions[jobId]?.[activeId]) : null
  const firstName = active ? active.full_name.split(' ')[0] : 'candidate'
  const fitLabel = activeMatch
    ? (activeMatch.relevance === 'strong' ? 'Strong fit' : activeMatch.relevance === 'moderate' ? 'Moderate fit' : 'Weak fit')
    : ''

  const requirementRows = useMemo(
    () => (job && active && activeMatch ? buildRows(job, active, activeMatch) : []),
    [job, active, activeMatch],
  )

  useEffect(() => {
    if (!draftOpen) return undefined
    function onKey(event) {
      if (event.key === 'Escape' && !draftBusy) setDraftOpen(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [draftOpen, draftBusy])

  const processed = totals.ready + totals.error + totals.blocked
  const progress = totals.total > 0 ? Math.round((processed / totals.total) * 100) : 0
  const rankingLabel = totals.total === 0
    ? 'No candidates'
    : processed >= totals.total
      ? `${totals.ready} scored${totals.error ? ` · ${totals.error} failed` : ''}${totals.blocked ? ` · ${totals.blocked} without resume` : ''}`
      : `Scoring ${processed} of ${totals.total}…`

  function selectCandidate(candidateId) {
    userPickedRef.current = true
    setActiveId(candidateId)
  }

  function changeJob(nextId) {
    if (!nextId || nextId === jobId) return
    userPickedRef.current = true
    setJobId(nextId)
    setDraftOpen(false)
  }

  function setDecision(candidateId, value) {
    if (!jobId) return
    setDecisions((prev) => {
      const forJob = { ...(prev[jobId] || {}) }
      if (value) forJob[candidateId] = value
      else delete forJob[candidateId]
      return { ...prev, [jobId]: forJob }
    })
  }

  function toggleShortlist() {
    if (!active) return
    if (activeDecision === 'shortlisted') {
      setDecision(active.id, null)
      flash(`${firstName} removed from the shortlist`)
    } else {
      setDecision(active.id, 'shortlisted')
      flash(`${firstName} shortlisted for this session`)
    }
  }

  function toggleNotShortlisted() {
    if (!active) return
    if (activeDecision === 'not_shortlisted') {
      setDecision(active.id, null)
      flash(`${firstName} restored to review`)
      return
    }
    if (activeDecision === 'shortlisted') {
      const confirmed = window.confirm(
        `Remove ${active.full_name} from the shortlist and mark them as not shortlisted for this role?`,
      )
      if (!confirmed) return
    }
    setDecision(active.id, 'not_shortlisted')
    flash(`${firstName} marked as not shortlisted`)
  }

  function openDraft() {
    if (!active || !job) return
    setDraftType('interview_invitation')
    setDraftNotes('')
    setDraftError('')
    setDraft(null)
    setCopied(false)
    setDraftOpen(true)
  }

  async function generateDraft() {
    if (!active || !job || draftBusy) return
    setDraftBusy(true)
    setDraftError('')
    setCopied(false)
    try {
      const response = await draftCommunication({
        draft_type: draftType,
        job_id: job.id,
        candidate_id: active.id,
        custom_notes: draftNotes.trim() || null,
      })
      setDraft(response.draft)
    } catch (err) {
      setDraftError(err instanceof ApiError ? err.message : 'Could not generate the draft.')
    } finally {
      setDraftBusy(false)
    }
  }

  async function copyDraft() {
    if (!draft) return
    const text = `Subject: ${draft.subject}\n\n${draft.body}`
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        const area = window.document.createElement('textarea')
        area.value = text
        window.document.body.appendChild(area)
        area.select()
        window.document.execCommand('copy')
        window.document.body.removeChild(area)
      }
      setCopied(true)
      flash('Draft copied to clipboard')
    } catch {
      flash('Could not copy the draft. Select the text manually.')
    }
  }

  if (loading) {
    return (
      <div className="page np">
        <header className="page-header">
          <div>
            <div className="eyebrow">AI matching</div>
            <h1 className="page-title">Matches</h1>
            <p className="page-sub">Compare job requirements with candidate profiles.</p>
          </div>
        </header>
        <div className="card cd-loading"><span className="spinner" aria-hidden="true" /> Loading jobs, candidates and resumes…</div>
      </div>
    )
  }

  if (loadError && jobs.length === 0 && candidates.length === 0) {
    return (
      <div className="page np">
        <header className="page-header">
          <div>
            <div className="eyebrow">AI matching</div>
            <h1 className="page-title">Matches</h1>
            <p className="page-sub">Compare job requirements with candidate profiles.</p>
          </div>
        </header>
        <div className="card cd-error">
          <NwIcon name="x-circle" />
          <h2>Could not load match data</h2>
          <p className="muted">{loadError}</p>
          <button type="button" className="btn btn-secondary" onClick={() => loadData()}>Retry</button>
        </div>
      </div>
    )
  }

  if (jobs.length === 0) {
    return (
      <div className="page np">
        <header className="page-header">
          <div>
            <div className="eyebrow">AI matching</div>
            <h1 className="page-title">Matches</h1>
            <p className="page-sub">Compare job requirements with candidate profiles.</p>
          </div>
        </header>
        <div className="card cd-empty">
          <NwIcon name="target" />
          <h2 className="card-title">No jobs yet</h2>
          <p className="muted">Create a role with required skills before comparing candidates.</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/jobs/new')}>Create a job</button>
        </div>
      </div>
    )
  }

  if (candidates.length === 0) {
    return (
      <div className="page np">
        <header className="page-header">
          <div>
            <div className="eyebrow">AI matching</div>
            <h1 className="page-title">Matches</h1>
            <p className="page-sub">Compare job requirements with candidate profiles.</p>
          </div>
        </header>
        <div className="card cd-empty">
          <NwIcon name="users" />
          <h2 className="card-title">No candidates yet</h2>
          <p className="muted">Add candidates and upload resumes to rank them against this role.</p>
          <button type="button" className="btn btn-primary" onClick={() => navigate('/candidates')}>Add candidates</button>
        </div>
      </div>
    )
  }

  return (
    <div className="page np">
      <header className="page-header mt-header">
        <div>
          <div className="eyebrow">AI matching</div>
          <h1 className="page-title">Matches</h1>
          <p className="page-sub">Compare job requirements with candidate profiles.</p>
        </div>
        <div className="page-actions">
          <button type="button" className="btn btn-secondary" onClick={() => loadData({ refresh: true })} disabled={refreshing}>
            <NwIcon name="refresh" className={refreshing ? 'mt-spin' : ''} /> {refreshing ? 'Refreshing…' : 'Refresh data'}
          </button>
          <button type="button" className="btn btn-secondary" aria-expanded={showWeights} onClick={() => setShowWeights((value) => !value)}>
            <NwIcon name="filter" /> Matching breakdown
          </button>
        </div>
      </header>

      <section className="card mt-jobbar" aria-label="Job selection">
        <label className="mt-jobpick">
          <span className="tile-mini"><NwIcon name="briefcase" /></span>
          <span className="mt-jobpick-body">
            <span className="eyebrow">Selected job</span>
            <span className="mt-select-wrap">
              <select className="mt-job-select" value={jobId || ''} onChange={(event) => changeJob(event.target.value)} aria-label="Select job">
                {jobs.map((row) => (
                  <option key={row.id} value={row.id}>{row.title}{row.company ? ` · ${row.company}` : ''}</option>
                ))}
              </select>
              <NwIcon name="chevron-down" />
            </span>
          </span>
        </label>
        {job && (
          <div className="mt-jobmeta">
            <span className="chip"><NwIcon name="pin" /> {job.location || 'Location not set'}</span>
            <span className="chip"><NwIcon name="clock" /> {job.experience_required !== null && job.experience_required !== undefined ? `${job.experience_required}+ years` : 'Experience not set'}</span>
            <span className="chip"><NwIcon name="target" /> {(job.required_skills || []).length} required skill{(job.required_skills || []).length === 1 ? '' : 's'}</span>
          </div>
        )}
        <div className="mt-jobbar-right">
          <span className={`chip ${job?.status === 'open' ? 'chip-green' : 'chip-gray'}`}>{job?.status === 'open' ? 'Open role' : 'Closed role'}</span>
        </div>
      </section>

      {loadError && (
        <div className="mt-banner" role="alert">
          <NwIcon name="x-circle" />
          <span>{loadError} Existing results are still shown below.</span>
          <button type="button" className="btn btn-sm btn-secondary" onClick={() => loadData({ refresh: true })} disabled={refreshing}>Retry</button>
        </div>
      )}

      {totals.error > 0 && (
        <div className="mt-banner mt-banner-warn" role="status">
          <NwIcon name="x-circle" />
          <span>{totals.error} candidate{totals.error === 1 ? '' : 's'} could not be scored. The rest of the ranking is still available.</span>
          <button type="button" className="btn btn-sm btn-secondary" onClick={retryFailed}>Retry failed</button>
        </div>
      )}

      {showWeights && (
        <section className="card card-pad mt-breakdown" aria-label="Matching breakdown">
          <div className="card-head">
            <h2 className="card-title">Matching breakdown</h2>
            <span className="muted">{active ? active.full_name : 'No candidate selected'}</span>
          </div>
          <div className="mt-breakdown-grid">
            <div className="mt-breakdown-item"><span>Matched skills</span><strong>{activeMatch ? activeMatch.matched_skills.length : 0}</strong></div>
            <div className="mt-breakdown-item"><span>Unverified skills</span><strong>{activeMatch ? activeMatch.unverified_skills.length : 0}</strong></div>
            <div className="mt-breakdown-item"><span>Missing skills</span><strong>{activeMatch ? activeMatch.missing_skills.length : 0}</strong></div>
            <div className="mt-breakdown-item"><span>Evidence quotes</span><strong>{activeMatch ? activeMatch.evidence.length : 0}</strong></div>
          </div>
          <p className="mt-breakdown-note muted">Counts come from the backend matching response for the selected candidate. The relevance score is returned by the API; this page does not compute it.</p>
        </section>
      )}

      <div className="mt-grid">
        <aside className="card mt-rank" aria-label="Candidate ranking">
          <div className="mt-rank-head">
            <div className="mt-rank-title">
              <h2>Candidate ranking</h2>
              <span className="chip chip-gray">{filtered.length} of {candidates.length}</span>
            </div>
            <div className="mt-rank-progress">
              <span className="mt-progress"><span style={{ width: `${progress}%` }} /></span>
              <small className="muted">{rankingLabel}</small>
            </div>
            <div className="mt-rank-filters">
              <div className="mt-search">
                <NwIcon name="search" />
                <input
                  className="input"
                  type="search"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search name or skill"
                  aria-label="Search candidates"
                />
              </div>
              <select className="select mt-filter" value={listFilter} onChange={(event) => setListFilter(event.target.value)} aria-label="Filter candidates">
                <option value="all">All ({filterCounts.all})</option>
                <option value="shortlisted">Shortlisted ({filterCounts.shortlisted})</option>
                <option value="not_shortlisted">Not shortlisted ({filterCounts.not_shortlisted})</option>
              </select>
            </div>
          </div>

          <div className="mt-rank-cols" aria-hidden="true">
            <span>S.No.</span>
            <span>Candidate</span>
            <span>Exp.</span>
            <span>Match</span>
          </div>

          <ul className="mt-rank-list">
            {filtered.map((row, index) => {
              const selected = row.candidate.id === activeId
              return (
                <li key={row.candidate.id}>
                  <button
                    type="button"
                    className={`mt-cand ${selected ? 'active' : ''}`}
                    aria-current={selected ? 'true' : undefined}
                    onClick={() => selectCandidate(row.candidate.id)}
                  >
                    <span className="mt-cand-no">{String(index + 1).padStart(2, '0')}</span>
                    <span className="mt-cand-who">
                      <Avatar name={row.candidate.full_name} size={28} />
                      <span className="mt-cand-text">
                        <strong>
                          {row.candidate.full_name}
                          {row.decision === 'shortlisted' && <NwIcon name="star" className="mt-cand-mark ok" />}
                          {row.decision === 'not_shortlisted' && <NwIcon name="x" className="mt-cand-mark no" />}
                        </strong>
                        <small>{row.candidate.email || (row.candidate.skills || []).slice(0, 2).join(', ') || 'No contact details'}</small>
                      </span>
                    </span>
                    <span className="mt-cand-exp">{typeof row.candidate.experience_years === 'number' ? `${row.candidate.experience_years} yrs` : '—'}</span>
                    <span className="mt-cand-score">
                      <CandidateScore entry={row.entry} />
                    </span>
                  </button>
                </li>
              )
            })}
            {filtered.length === 0 && (
              <li className="mt-rank-empty muted">No candidates match these filters.</li>
            )}
          </ul>

          <div className="mt-rank-foot">
            <NwIcon name="shield" /> Completed results are cached and reused until the resume, job, or matching logic changes.
          </div>
        </aside>

        <main className="mt-main">
          <section className="card mt-context" aria-label="Selected job and candidate">
            <div className="mt-context-block">
              <div className="eyebrow">Selected job</div>
              <div className="mt-context-head">
                <span className="tile-mini"><NwIcon name="briefcase" /></span>
                <div>
                  <strong>{job?.title || 'No job selected'}</strong>
                  <small className="muted">{job?.company || 'Company not set'}</small>
                </div>
              </div>
              <div className="mt-context-meta">
                <span><NwIcon name="pin" /> {job?.location || 'Location not set'}</span>
                <span><NwIcon name="clock" /> {job?.experience_required !== null && job?.experience_required !== undefined ? `${job.experience_required}+ years` : 'Experience not set'}</span>
              </div>
              <div className="mt-skill-chips">
                {(job?.required_skills || []).length > 0
                  ? job.required_skills.map((skill) => <span key={skill} className="chip chip-indigo">{skill}</span>)
                  : <span className="muted mt-context-empty">No required skills listed</span>}
              </div>
            </div>

            <div className="mt-context-block">
              <div className="eyebrow">Selected candidate</div>
              {active ? (
                <>
                  <div className="mt-context-head">
                    <Avatar name={active.full_name} size={34} />
                    <div>
                      <strong>{active.full_name}</strong>
                      <small className="muted">{active.email || 'Email not provided'}</small>
                    </div>
                  </div>
                  <div className="mt-context-meta">
                    <span><NwIcon name="clock" /> {typeof active.experience_years === 'number' ? `${active.experience_years} years` : 'Experience not parsed'}</span>
                    <span><NwIcon name="file" /> {activeRow?.info.label || 'Resume status unavailable'}</span>
                  </div>
                  <div className="mt-skill-chips">
                    {(active.skills || []).length > 0
                      ? active.skills.slice(0, 8).map((skill) => <span key={skill} className="chip">{skill}</span>)
                      : <span className="muted mt-context-empty">No skills listed</span>}
                  </div>
                </>
              ) : (
                <p className="muted mt-context-empty">Select a candidate from the ranking.</p>
              )}
            </div>
          </section>

          <section className="card mt-compare" aria-label="Requirement comparison">
            <div className="mt-compare-head">
              <div>
                <div className="eyebrow">Requirement comparison</div>
                <h2>{job?.title || 'Role'} <span className="muted">vs</span> {active?.full_name || 'candidate'}</h2>
              </div>
              <div className="mt-compare-tools">
                {activeScore !== null && (
                  <span className="mt-score-chip" style={{ color: scoreColor(activeScore), borderColor: scoreColor(activeScore) }}>{activeScore}% match</span>
                )}
                {cacheStatusLabel(activeEntry) && (
                  <span className="chip chip-gray">{cacheStatusLabel(activeEntry)}</span>
                )}
                <div className="mt-legend-row" aria-label="Legend">
                  <span><i className="matched" /> Matched</span>
                  <span><i className="partial" /> Partial</span>
                  <span><i className="missing" /> Missing</span>
                </div>
              </div>
            </div>

            {!activeEntry || activeEntry.status === 'pending' ? (
              <div className="mt-wait"><span className="spinner" aria-hidden="true" /><span>Queued for scoring…</span></div>
            ) : activeEntry.status === 'loading' ? (
              <div className="mt-wait"><span className="spinner" aria-hidden="true" /><span>Mitra is comparing the resume with this role…</span></div>
            ) : activeEntry.status === 'blocked' ? (
              <div className="mt-inline-error mt-inline-error-neutral">
                <NwIcon name="file" />
                <div>
                  <strong>No resume on file</strong>
                  <p>{activeEntry.error} Upload a resume to run the comparison.</p>
                </div>
                {active && <button type="button" className="btn btn-sm btn-secondary" onClick={() => navigate(`/candidates/${active.id}`)}>Open candidate</button>}
              </div>
            ) : activeEntry.status === 'error' ? (
              <div className="mt-inline-error">
                <NwIcon name="x-circle" />
                <div>
                  <strong>Could not score this candidate</strong>
                  <p>{activeEntry.error}</p>
                </div>
                {active && <button type="button" className="btn btn-sm btn-secondary" onClick={() => retryCandidate(active.id)}>Retry</button>}
              </div>
            ) : (
              <>
                <div className="mt-table-wrap">
                  <table className="mt-req-table">
                    <thead>
                      <tr>
                        <th>Requirement</th>
                        <th>Job requirement</th>
                        <th>Candidate evidence</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {requirementRows.length === 0 && (
                        <tr>
                          <td colSpan={4} className="muted">This job has no required skills or experience target to compare.</td>
                        </tr>
                      )}
                      {requirementRows.map((row) => (
                        <tr key={row.key}>
                          <td>
                            <div className="mt-req-name">{row.label}<small>{row.note}</small></div>
                          </td>
                          <td className="mt-req-job">{row.jobReq}</td>
                          <td className="mt-req-evidence">
                            {row.source ? <q>{row.evidenceText}</q> : row.evidenceText}
                            {row.source && <small>Source: {row.source}</small>}
                          </td>
                          <td>
                            <span className={`mt-status-pill ${row.status}`}>
                              <NwIcon name={STATUS_META[row.status].icon} /> {row.statusLabel}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="mt-reason">
                  <div>
                    <div className="eyebrow">Why this candidate</div>
                    <p>{activeMatch?.explanation}</p>
                  </div>

                  <div className="mt-skill-groups">
                    <div className="mt-skill-group">
                      <div className="eyebrow">Matched · {activeMatch ? activeMatch.matched_skills.length : 0}</div>
                      <div className="mt-skill-chips">
                        {activeMatch && activeMatch.matched_skills.length > 0
                          ? activeMatch.matched_skills.map((skill) => <span key={skill} className="chip chip-green">{skill}</span>)
                          : <span className="muted">None</span>}
                      </div>
                    </div>
                    <div className="mt-skill-group">
                      <div className="eyebrow">Partial · {activeMatch ? activeMatch.unverified_skills.length : 0}</div>
                      <div className="mt-skill-chips">
                        {activeMatch && activeMatch.unverified_skills.length > 0
                          ? activeMatch.unverified_skills.map((skill) => <span key={skill} className="chip chip-amber">{skill}</span>)
                          : <span className="muted">None</span>}
                      </div>
                    </div>
                    <div className="mt-skill-group">
                      <div className="eyebrow">Missing · {activeMatch ? activeMatch.missing_skills.length : 0}</div>
                      <div className="mt-skill-chips">
                        {activeMatch && activeMatch.missing_skills.length > 0
                          ? activeMatch.missing_skills.map((skill) => <span key={skill} className="chip chip-coral">{skill}</span>)
                          : <span className="muted">None</span>}
                      </div>
                    </div>
                  </div>

                  <div>
                    <div className="eyebrow">Resume evidence · {activeMatch ? activeMatch.evidence.length : 0}</div>
                    {activeMatch && activeMatch.evidence.length > 0 ? (
                      <ul className="mt-evidence-list">
                        {activeMatch.evidence.map((item, index) => (
                          <li key={`${item.source}-${index}`} className="mt-evidence-item">
                            <q>{item.quote}</q>
                            <small>Source: {item.source}</small>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-no-evidence">No supporting resume quotes were returned for this match. The comparison is based on the structured matching result only.</p>
                    )}
                  </div>
                </div>
              </>
            )}
          </section>
        </main>

        <aside className="mt-side">
          {job && (
            <section className="card card-pad mt-external">
              <div className="card-head">
                <h2 className="card-title">Job search</h2>
              </div>
              <p className="muted mt-external-note">Open current listings for this role in a new tab. Mitra does not fetch, scrape, or send candidate data.</p>
              <JobSearch role={job.title} location={job.location || ''} />
            </section>
          )}

          <section className="card card-pad mt-scorecard">
            <div className="card-head">
              <h2 className="card-title">Match score</h2>
              {cacheStatusLabel(activeEntry) && (
                <span className={`chip ${activeEntry.cacheStatus === 'hit' ? 'chip-gray' : 'chip-green'}`}>
                  {cacheStatusLabel(activeEntry)}
                </span>
              )}
            </div>
            {activeEntry?.status === 'ready' && activeMatch ? (
              <>
                <div className="mt-score-top">
                  <ScoreRing score={activeScore} size={120} stroke={10} />
                  <div className="mt-score-summary">
                    <strong style={{ color: scoreColor(activeScore) }}>{fitLabel}</strong>
                    <span className="mt-score-state"><i className="mt-dot ok" /> {activeEntry.cacheStatus === 'hit' ? 'Cached result' : 'Fresh analysis'}</span>
                    <p>{activeMatch.matched_skills.length} matched · {activeMatch.unverified_skills.length} partial · {activeMatch.missing_skills.length} missing</p>
                  </div>
                </div>
                <div className="mt-score-counts">
                  <div className="mt-score-count matched"><b>{activeMatch.matched_skills.length}</b><small>Matched</small></div>
                  <div className="mt-score-count partial"><b>{activeMatch.unverified_skills.length}</b><small>Partial</small></div>
                  <div className="mt-score-count missing"><b>{activeMatch.missing_skills.length}</b><small>Missing</small></div>
                </div>
                <p className="mt-score-explain">This is the backend matching result on a 0–100 scale. It reflects the relevance of the candidate’s parsed resume to this job’s required skills and experience. This page does not calculate or adjust the score.</p>
                <button type="button" className="btn btn-sm btn-secondary" onClick={() => retryCandidate(active.id, { forceRefresh: true })} disabled={!active || Boolean(getInflightMatch(`${jobId}:${active.id}`))}>
                  <NwIcon name="refresh" /> Recalculate match
                </button>
              </>
            ) : activeEntry?.status === 'error' ? (
              <div className="mt-score-empty">
                <span className="mt-ring-empty error" aria-hidden="true">!</span>
                <strong>Score unavailable</strong>
                <p className="muted">{activeEntry.error}</p>
                {active && (
                  <button type="button" className="btn btn-sm btn-secondary" onClick={() => retryCandidate(active.id)}>
                    <NwIcon name="refresh" /> Retry scoring
                  </button>
                )}
              </div>
            ) : (
              <div className="mt-score-empty">
                <span className="mt-ring-empty" aria-hidden="true">—</span>
                <p className="muted">
                  {!active
                    ? 'Select a candidate to see the score.'
                    : activeEntry?.status === 'loading'
                      ? 'Scoring this candidate…'
                      : activeEntry?.status === 'blocked'
                        ? 'No resume is available for this candidate.'
                        : 'This candidate is queued for scoring.'}
                </p>
              </div>
            )}
          </section>

          <section className="card card-pad mt-actions" aria-label="Recruiter actions">
            <div className="card-head">
              <h2 className="card-title">Recruiter actions</h2>
              <span className={`chip ${activeDecision === 'shortlisted' ? 'chip-green' : activeDecision === 'not_shortlisted' ? 'chip-coral' : 'chip-gray'}`}>
                {activeDecision === 'shortlisted' ? 'Shortlisted' : activeDecision === 'not_shortlisted' ? 'Not shortlisted' : 'Not reviewed'}
              </span>
            </div>
            <div className="mt-action-stack">
              <button type="button" className={`btn btn-block ${activeDecision === 'shortlisted' ? 'btn-secondary' : 'btn-primary'}`} onClick={toggleShortlist} disabled={!active}>
                <NwIcon name={activeDecision === 'shortlisted' ? 'check-circle' : 'star'} /> {activeDecision === 'shortlisted' ? `Remove ${firstName} from shortlist` : `Shortlist ${firstName}`}
              </button>
              <button type="button" className={`btn btn-block btn-ghost ${activeDecision === 'not_shortlisted' ? 'mt-decision-off' : ''}`} onClick={toggleNotShortlisted} disabled={!active}>
                <NwIcon name={activeDecision === 'not_shortlisted' ? 'refresh' : 'x'} /> {activeDecision === 'not_shortlisted' ? 'Undo not shortlisted' : 'Mark as not shortlisted'}
              </button>
              <button type="button" className="btn btn-block btn-secondary" onClick={openDraft} disabled={!active || !job}>
                <NwIcon name="mail" /> Draft email
              </button>
              <button type="button" className="btn btn-block btn-secondary" onClick={() => active && navigate(`/candidates/${active.id}`)} disabled={!active}>
                <NwIcon name="file" /> View resume &amp; evidence
              </button>
            </div>
            <p className="mt-local-note"><NwIcon name="shield" /> Shortlist and not-shortlisted decisions are kept in this browser session only. They are not saved to the backend.</p>
          </section>
        </aside>
      </div>

      {draftOpen && active && job && (
        <div className="mt-modal-backdrop" onClick={(event) => { if (event.target === event.currentTarget && !draftBusy) setDraftOpen(false) }}>
          <section className="card mt-modal" role="dialog" aria-modal="true" aria-labelledby="mt-draft-title">
            <div className="mt-modal-head">
              <div>
                <h2 id="mt-draft-title">Draft email</h2>
                <p className="muted mt-modal-sub">AI-generated draft for review. Nothing is sent from this page.</p>
              </div>
              <button type="button" className="icon-btn" aria-label="Close" onClick={() => { if (!draftBusy) setDraftOpen(false) }}>
                <NwIcon name="x" />
              </button>
            </div>
            <div className="mt-modal-body">
              <div className="mt-modal-to">
                <Avatar name={active.full_name} size={26} />
                <span><strong>{active.full_name}</strong>{active.email ? ` · ${active.email}` : ''}</span>
                <span className="muted">· {job.title}</span>
              </div>
              <div className="mt-modal-grid">
                <label className="field">
                  <span className="eyebrow">Email type</span>
                  <select className="select" value={draftType} onChange={(event) => { setDraftType(event.target.value); setDraft(null); setDraftError('') }} disabled={draftBusy}>
                    {DRAFT_TYPES.map((type) => <option key={type.value} value={type.value}>{type.label}</option>)}
                  </select>
                </label>
                <label className="field">
                  <span className="eyebrow">Notes for Mitra (optional)</span>
                  <textarea className="textarea" rows={2} value={draftNotes} onChange={(event) => setDraftNotes(event.target.value)} placeholder="Tone, availability, next steps…" disabled={draftBusy} />
                </label>
              </div>
              <button type="button" className="btn btn-primary" onClick={generateDraft} disabled={draftBusy}>
                {draftBusy
                  ? <><span className="spinner mt-spinner-sm" aria-hidden="true" /> Generating…</>
                  : <><NwIcon name="sparkle" /> {draft ? 'Regenerate draft' : 'Generate draft'}</>}
              </button>
              {draftError && <p className="mt-draft-error" role="alert"><NwIcon name="x-circle" /> {draftError}</p>}
              {draft && (
                <div className="mt-draft-preview">
                  <label className="field">
                    <span className="eyebrow">Subject</span>
                    <input className="input" value={draft.subject} onChange={(event) => setDraft({ ...draft, subject: event.target.value })} />
                  </label>
                  <label className="field">
                    <span className="eyebrow">Body</span>
                    <textarea className="textarea mt-draft-body" value={draft.body} onChange={(event) => setDraft({ ...draft, body: event.target.value })} />
                  </label>
                  <p className="mt-draft-note"><NwIcon name="shield" /> {draft.requires_approval ? 'This draft requires your approval before use.' : 'Review this draft before use.'} Copy it or open Messages to continue the existing workflow.</p>
                </div>
              )}
            </div>
            <div className="mt-modal-foot">
              <button type="button" className="btn btn-ghost" onClick={() => setDraftOpen(false)} disabled={draftBusy}>Close</button>
              <button type="button" className="btn btn-secondary" onClick={() => { setDraftOpen(false); navigate('/messages') }} disabled={draftBusy}>Open Messages</button>
              <button type="button" className="btn btn-primary" onClick={copyDraft} disabled={!draft || draftBusy}>
                <NwIcon name={copied ? 'check' : 'download'} /> {copied ? 'Copied' : 'Copy draft'}
              </button>
            </div>
          </section>
        </div>
      )}

      {toast && (
        <div className="toast" role="status">
          <NwIcon name="check" /> {toast}
        </div>
      )}
    </div>
  )
}
