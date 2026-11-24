import { useEffect, useMemo, useRef, useState } from 'react'
import NwIcon from './NwIcon'
import {
  createChatSession,
  deleteAllChatSessions,
  deleteChatSession,
  listChatMessages,
  listChatSessions,                                                                                     
  renameChatSession,
  sendChatMessage,
} from '../services/chat'

import {
  createInterviewSession,
  getCurrentInterviewSession,
  getInterviewQuestion,
  listInterviewQuestions,
  startInterviewSession,
  submitInterviewAnswer,
  completeInterviewSession,
  uploadInterviewResume,
  deleteInterviewResume,
} from '../services/interviews'
import { listDocuments, uploadDocument } from '../services/rag'
import { moveSessionToTop, sessionTimeLabel, toChatMessage } from '../utils/chat'
import {
  buildConversationPrintHtml,
  buildInterviewPrintHtml,
  conversationExportFilename,
  interviewReportFilename,
  openPrintDocument,
} from '../utils/chatExport'

const GREETING_PATTERN =
  /^(hi+|hello+|hey+(?:\s+there)?|good\s+(?:morning|afternoon|evening)|thanks(?:\s+you)?|thank\s+you|how\s+are\s+you(?:\s+doing)?|what'?s\s+up|howdy|greetings|yo)\b[\s!.?,]*$/i

const GREETING_REPLY =
  "Hello! I'm your recruiter AI assistant. I can answer questions about your uploaded documents, candidates, and jobs — for example: summarize a candidate, find who has specific skills, or explain a job's requirements. Ask me a recruitment question to get started."

const SUGGESTED_QUESTIONS = [
  'Summarize my candidates.',
  'Find candidates matching a job.',
  'Explain the requirements of my latest job.',
  "Identify missing skills in a candidate's profile.",
]

const CANDIDATE_GREETING_REPLY =
  "Hello! I'm your AI assistant. I can help you improve your resume, plan your career, prepare for interviews, and understand job requirements. Ask me a question to get started.";

const CANDIDATE_SUGGESTED_QUESTIONS = [
  'How can I improve my resume?',
  'Analyze my skills and suggest career growth.',
  'Help me prepare for my next interview.',
  "Explain my application status and next steps.",
  'Suggest skills to strengthen my profile for a target role.',
];

const AGENTS = [
  { icon: 'target', name: 'Job Analysis' },
  { icon: 'file', name: 'Resume Parsing' },
  { icon: 'users', name: 'Candidate Matching' },
  { icon: 'calendar', name: 'Interview Scheduling' },
  { icon: 'sparkle', name: 'Recruiter Support', active: true },
]

const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md']
const MAX_UPLOAD_BYTES = 20 * 1024 * 1024
const MAX_CHAT_SESSIONS_PER_USER = 10

const INTERVIEW_ACCEPTED_EXTENSIONS = ['.pdf', '.docx']
const INTERVIEW_MAX_UPLOAD_BYTES = 20 * 1024 * 1024

const INTERVIEW_DEFAULTS = {
  interview_type: 'Technical + HR',
  total_questions: 10,
  difficulty: 'Adaptive',
  mode: 'Text-based',
}

const INTERVIEW_WELCOME =
  'Welcome to AI Mock Interview. Upload your resume and I will analyze it to prepare a personalized interview session. Once your resume is processed, you can start the interview.'

const INTERVIEW_DIFFICULTY_PROGRESSION = 'Easy → Medium → Hard'

function formatProfileItems(value) {
  if (Array.isArray(value)) {
    return value
      .map((item) => {
        if (item && typeof item === 'object') {
          if (item.title || item.company || item.period) {
            const head = [item.title, item.company, item.period].filter(Boolean).join(' — ')
            const details = [
              ...(Array.isArray(item.responsibilities) ? item.responsibilities : []).map((line) => `• ${line}`),
              ...(Array.isArray(item.achievements) ? item.achievements : []).map((line) => `✓ ${line}`),
            ]
            return details.length ? `${head}\n${details.join('\n')}` : head
          }
          if (item.title) {
            const tech = (Array.isArray(item.technologies) ? item.technologies : []).join(', ')
            const description = (Array.isArray(item.description) ? item.description : []).join(' ')
            return [item.title, tech ? `Technologies: ${tech}` : '', description]
              .filter(Boolean)
              .join('\n')
          }
        }
        return item == null ? '' : String(item)
      })
      .filter(Boolean)
  }
  if (typeof value === 'string' && value.trim()) return [value.trim()]
  return []
}

function formatInterviewExperience(items) {
  return formatProfileItems(items)
}

function interviewInfoValue(value) {
  return formatProfileItems(value)
}

function interviewMessageId(kind, number) {
  return `interview-${kind}-${number}`
}

function interviewQuestionMessage(question) {
  return {
    id: interviewMessageId('question', question.question_number),
    role: 'assistant',
    text: `Question ${question.question_number} of ${question.total_questions || 10}:\n\n${question.question_text}`,
    time: nowLabel(),
    sources: [],
    hasEvidence: true,
  }
}

function interviewAnswerMessage(number, text) {
  return {
    id: interviewMessageId('answer', number),
    role: 'user',
    text,
    time: nowLabel(),
  }
}

function trimSentences(value, max = 3) {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  if (!text) return ''
  const parts = text.match(/[^.!?]+(?:[.!?]+|$)/g) || [text]
  return parts.slice(0, max).map((part) => part.trim()).filter(Boolean).join(' ')
}

const SOURCE_TYPES = [
  { value: 'resume', label: 'Resume' },
  { value: 'job_description', label: 'Job description' },
  { value: 'knowledge', label: 'Knowledge base' },
]

const SOURCE_LABELS = SOURCE_TYPES.reduce((map, item) => {
  map[item.value] = item.label
  return map
}, {})

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function SpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M3 10v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z" />
      <path d="M8 2v4M16 2v4M9 8h6" />
    </svg>
  )
}

function StopSpeakerIcon() {
  return (
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" />
    </svg>
  )
}

function PencilIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 20h4l10-10-4-4L4 16v4Z" strokeLinejoin="round" />
      <path d="m13 6 4 4" strokeLinecap="round" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

function sourceLine(source) {
  if (!source) return ''
  if (typeof source !== 'object') return String(source)
  const parts = [source.source_type, source.filename || source.source]
  if (source.chunk_index !== undefined) parts.push(`chunk ${source.chunk_index}`)
  if (source.score !== undefined) parts.push(`score ${Number(source.score).toFixed(3)}`)
  return parts.filter(Boolean).join(' · ')
}

function JobResults({ items }) {
  return (
    <div className="as-jobs">
      <table className="as-jobs-table">
        <thead>
          <tr>
            <th>Job Title</th>
            <th>Company</th>
            <th>Location</th>
            <th>Experience</th>
            <th>Type</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          {items.map((job, index) => (
            <tr key={`${job.url || index}-${index}`}>
              <td>
                <a href={job.url} target="_blank" rel="noopener noreferrer">{job.title || 'Not specified'}</a>
              </td>
              <td>{job.company || 'Not specified'}</td>
              <td>{job.location || 'Not specified'}</td>
              <td>{job.experience || 'Not specified'}</td>
              <td>{job.employment_type || 'Not specified'}</td>
              <td>{job.source || 'Not specified'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <details className="as-jobs-details">
        <summary>Job details</summary>
        {items.map((job, index) => (
          <div key={`${job.url || index}-detail-${index}`} className="as-job-detail">
            <strong>{job.title || 'Not specified'}</strong>
            <p>{job.description || 'Not specified'}</p>
            <p>Skills: {(job.skills || []).join(', ') || 'Not specified'}</p>
            <p>Salary: {job.salary || 'Not specified'}</p>
            <p>Found: {job.search_date || 'Not specified'}</p>
            {job.url && <a href={job.url} target="_blank" rel="noopener noreferrer">View original posting</a>}
          </div>
        ))}
      </details>
    </div>
  )
}

function messageSources(message) {
  const sources = Array.isArray(message.sources) ? message.sources : []
  const jobs = sources.filter((item) => item?.kind === 'job')
  const documents = sources.filter((item) => !item?.kind || item.kind === 'document')
  return (
    <>
      {jobs.length > 0 && <JobResults items={jobs} />}
      {documents.length > 0 && (
        <ol className="as-sources">
          {documents.map((source, index) => (
            <li key={index}>
              <span className="as-num">{index + 1}</span>
              <span>{sourceLine(source)}</span>
            </li>
          ))}
        </ol>
      )}
    </>
  )
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 KB'
  if (bytes < 1024) return `${bytes} B`
  const kilobytes = bytes / 1024
  if (kilobytes < 1024) return `${kilobytes < 10 ? kilobytes.toFixed(1) : Math.round(kilobytes)} KB`
  const megabytes = kilobytes / 1024
  return `${megabytes < 10 ? megabytes.toFixed(1) : Math.round(megabytes)} MB`
}

function extensionOf(name) {
  const index = name.lastIndexOf('.')
  return index === -1 ? '' : name.slice(index).toLowerCase()
}

function validateFile(file) {
  if (!file) return 'Choose a file to upload.'
  if (!ACCEPTED_EXTENSIONS.includes(extensionOf(file.name))) {
    return `Unsupported file type. Use ${ACCEPTED_EXTENSIONS.join(', ')}.`
  }
  if (file.size === 0) return 'That file is empty.'
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${formatBytes(file.size)}. The limit is ${formatBytes(MAX_UPLOAD_BYTES)} per file.`
  }
  return ''
}

function sourceTypeForFile(name = '') {
  const value = String(name).toLowerCase()
  if (/(job|jd|requisition|vacancy|role)/.test(value)) return 'job_description'
  if (/(resume|cv|profile)/.test(value)) return 'resume'
  return 'knowledge'
}

function jobContextFromMessages(items = []) {
  let preferences = null
  let awaitingResponse = false
  for (const item of items) {
    if (item?.role !== 'assistant') continue
    for (const source of item.sources || []) {
      if (source?.kind === 'job_search_prompt') {
        awaitingResponse = true
        if (source.preferences) preferences = { kind: 'job_preferences', ...source.preferences }
      }
      if (source?.kind === 'job_preferences') {
        preferences = source
        awaitingResponse = false
      }
    }
  }
  return { preferences, awaitingResponse }
}

function toMessageAttachment(attachment) {
  return {
    id: attachment.documentId || attachment.id,
    documentId: attachment.documentId,
    name: attachment.name,
    size: attachment.size || 0,
    sourceType: attachment.sourceType,
    chunkCount: attachment.chunkCount ?? null,
    status: attachment.status || 'indexed',
  }
}

function messageAttachmentsFromSources(sources = [], docById = new Map()) {
  const byDocument = new Map()
  for (const source of sources) {
    const id = source?.document_id
    if (!id || byDocument.has(id)) continue
    const doc = docById.get(id) || {}
    byDocument.set(id, {
      id: `scope-${id}`,
      documentId: id,
      name: doc.filename || source.filename || id.slice(0, 8),
      size: doc.byte_size || 0,
      sourceType: doc.source_type || source.source_type || 'knowledge',
      chunkCount: doc.chunk_count ?? null,
      status: 'indexed',
    })
  }
  return [...byDocument.values()]
}

function annotateMessagesWithAttachments(items, docById) {
  const next = items.map((item) => ({ ...item }))
  for (let index = 1; index < next.length; index += 1) {
    if (next[index].role !== 'assistant' || next[index - 1].role !== 'user') continue
    next[index - 1].attachments = messageAttachmentsFromSources(
      next[index].sources,
      docById,
    )
  }
  return next
}

function mergeScope(current, additions) {
  const merged = new Map()
  for (const item of [...current, ...additions]) {
    if (item.documentId) merged.set(item.documentId, item)
  }
  return [...merged.values()]
}

export default function AssistantPage({ mode = 'recruiter' }) {
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [chatError, setChatError] = useState('')
  const [chatNotice, setChatNotice] = useState('')
  const [uploadError, setUploadError] = useState('')
  const [messages, setMessages] = useState([])
  const [interviewMessages, setInterviewMessages] = useState([])
  const [activeMode, setActiveMode] = useState(() => {
    try {
      return window.sessionStorage.getItem('mitraActiveMode') === 'interview' ? 'interview' : 'chat'
    } catch {
      return 'chat'
    }
  })
  const [lastQuestion, setLastQuestion] = useState('')
  const [messagesLoading, setMessagesLoading] = useState(false)
  const recruiterMode = mode !== 'candidate'

  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionsError, setSessionsError] = useState('')
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [creatingSession, setCreatingSession] = useState(false)
  const [deletingSessionId, setDeletingSessionId] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [renaming, setRenaming] = useState(false)

  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const [clearingHistory, setClearingHistory] = useState(false)
  const [historyNotice, setHistoryNotice] = useState('')
  const [historyError, setHistoryError] = useState('')

  const [isListening, setIsListening] = useState(false)
  const [recognition, setRecognition] = useState(null)
  const [voiceReplyError, setVoiceReplyError] = useState('')
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [speakingMessageId, setSpeakingMessageId] = useState(null)
  const speechUtteranceRef = useRef(null)

  const [attachments, setAttachments] = useState([])
  const [documentScope, setDocumentScope] = useState([])
  const [uploadingAttachmentId, setUploadingAttachmentId] = useState(null)
  const [historyOpen, setHistoryOpen] = useState(false)
  const [teamOpen, setTeamOpen] = useState(false)
  const [chatLimitOpen, setChatLimitOpen] = useState(false)

  const [interviewOpen, setInterviewOpen] = useState(false)
  const [interviewLoading, setInterviewLoading] = useState(true)
  const [interviewSession, setInterviewSession] = useState(null)
  const [interviewError, setInterviewError] = useState('')
  const [interviewUploading, setInterviewUploading] = useState(false)
  const [interviewUploadPhase, setInterviewUploadPhase] = useState('')
  const [interviewFileName, setInterviewFileName] = useState('')
  const [interviewStarting, setInterviewStarting] = useState(false)
  const [interviewStartError, setInterviewStartError] = useState('')
  const [interviewNextLoading, setInterviewNextLoading] = useState(false)
  const [interviewStarted, setInterviewStarted] = useState(false)
  const [interviewQuestion, setInterviewQuestion] = useState(null)
  const [interviewSubmitting, setInterviewSubmitting] = useState(false)
  const [interviewAnswerHistory, setInterviewAnswerHistory] = useState([])
  const [interviewReport, setInterviewReport] = useState(null)
  const [interviewCompleting, setInterviewCompleting] = useState(false)
  const [interviewReportExporting, setInterviewReportExporting] = useState(false)
  const interviewFileInputRef = useRef(null)
  const interviewRestoreRef = useRef(false)
  const interviewStartRef = useRef(false)
  const interviewSubmitRef = useRef(false)
  const interviewSessionFetchRef = useRef(false)
  const interviewFlowRef = useRef(false)

  const messageRequestId = useRef(0)
  const creatingSessionRef = useRef(false)
  const activeSessionRef = useRef(null)
  const messagesRef = useRef(null)
  const fileInputRef = useRef(null)
  const activeRequestRef = useRef(null)
  const stopRequestedRef = useRef(false)
  const textareaRef = useRef(null)

  const activeSession = useMemo(
    () => sessions.find((item) => item.id === activeSessionId) || null,
    [sessions, activeSessionId],
  )

  const interviewAnsweredCount = interviewAnswerHistory.length
  const interviewProgressPercent = interviewQuestion?.total_questions
    ? Math.min(100, Math.round((interviewAnsweredCount / interviewQuestion.total_questions) * 100))
    : 0

  const resumeSummary = (() => {
    const info = interviewSession?.extracted_info
    if (!info) return null
    const skills = [...(Array.isArray(info.technical_skills) ? info.technical_skills : []), ...(Array.isArray(info.design_skills) ? info.design_skills : [])]
      .map((item) => String(item || '').trim())
      .filter(Boolean)
      .filter((item, index, all) => all.findIndex((value) => value.toLowerCase() === item.toLowerCase()) === index)
      .slice(0, 8)
    return {
      candidate: info.candidate_name || null,
      role: info.job_title || null,
      experience: info.total_experience || null,
      location: info.location || null,
      skills,
      summary: trimSentences(info.professional_summary || info.summary || '', 3),
      projects: (Array.isArray(info.projects) ? info.projects : [])
        .map((project) => (project && typeof project === 'object' ? project.title : project))
        .filter(Boolean)
        .slice(0, 2),
    }
  })()

  const extractedFields = interviewSession?.extracted_info
    ? [
        ['Candidate name', interviewSession.extracted_info.candidate_name],
        ['Job title', interviewSession.extracted_info.job_title],
        ['Location', interviewSession.extracted_info.location],
        ['Email', interviewSession.extracted_info.email],
        ['Phone', interviewSession.extracted_info.phone],
        ['Total experience', interviewSession.extracted_info.total_experience],
        ['Professional summary', interviewSession.extracted_info.professional_summary],
        ['Technical skills', interviewSession.extracted_info.technical_skills],
        ['Design skills', interviewSession.extracted_info.design_skills],
        ['Work experience', interviewSession.extracted_info.work_experience],
        ['Projects', interviewSession.extracted_info.projects],
        ['Education', interviewSession.extracted_info.education],
        ['Certifications', interviewSession.extracted_info.certifications],
        ['Responsibilities', interviewSession.extracted_info.responsibilities],
        ['Achievements', interviewSession.extracted_info.achievements],
      ].filter(([, value]) => formatProfileItems(value).length > 0)
    : []

  const groups = useMemo(() => {
    const today = new Date()
    const startOfToday = new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime()
    const startOfWeek = new Date(
      today.getFullYear(),
      today.getMonth(),
      today.getDate() - ((today.getDay() + 6) % 7),
    ).getTime()
    const buckets = [
      { name: 'Today', items: [] },
      { name: 'This Week', items: [] },
      { name: 'Earlier', items: [] },
    ]
    sessions.forEach((session) => {
      const date = session.updated_at ? new Date(session.updated_at) : null
      const timestamp = date && !Number.isNaN(date.getTime()) ? date.getTime() : 0
      let bucketIndex = 2
      if (timestamp >= startOfToday) bucketIndex = 0
      else if (timestamp >= startOfWeek) bucketIndex = 1
      buckets[bucketIndex].items.push(session)
    })
    return buckets.filter((bucket) => bucket.items.length > 0)
  }, [sessions])

  useEffect(() => {
    const container = messagesRef.current
    if (container) container.scrollTop = container.scrollHeight
  }, [messages.length, interviewMessages.length, asking, messagesLoading, activeSessionId, activeMode])


  useEffect(() => {
    if (!recruiterMode || !interviewOpen) return
    if (interviewSession?.status !== 'in_progress') return
    if (interviewQuestion) return
    if (interviewSessionFetchRef.current) return
    interviewSessionFetchRef.current = true
    refreshInterviewQuestion(interviewSession.id).finally(() => {
      interviewSessionFetchRef.current = false
    })

  }, [recruiterMode, interviewOpen, interviewSession?.id, interviewSession?.status, interviewQuestion?.question_number])

  useEffect(() => {
    const textarea = textareaRef.current
    if (!textarea) return
    textarea.style.height = 'auto'
    const nextHeight = Math.min(textarea.scrollHeight, 140)
    textarea.style.height = `${nextHeight}px`
    textarea.style.overflowY = textarea.scrollHeight > 140 ? 'auto' : 'hidden'
  }, [question])

  useEffect(() => {
    activeSessionRef.current = activeSessionId
  }, [activeSessionId])

  useEffect(() => {
    let active = true
    async function restoreChat() {
      setSessionsLoading(true)
      setSessionsError('')
      try {
        const data = await listChatSessions()
        if (!active) return
        const list = Array.isArray(data) ? data : []
        setSessions((current) => {
          const fetched = new Map(list.map((session) => [session.id, session]))
          const localOnly = current.filter((session) => !fetched.has(session.id))
          return [...localOnly, ...list]
        })
        if (list.length > 0 && !activeSessionRef.current) {
          await openSession(list[0].id)
        }
      } catch (err) {
        if (active) setSessionsError(err.message)
      } finally {
        if (active) setSessionsLoading(false)
      }
    }

    restoreChat()
    return () => {
      active = false
      messageRequestId.current += 1
    }
  }, [])

  useEffect(() => {
    if (!recruiterMode) return
    let active = true
    async function restoreInterview() {
      setInterviewLoading(true)
      try {
        const session = await getCurrentInterviewSession()
        if (!active) return
        if (session && session.status !== 'completed') {
          setInterviewSession(session)
          setInterviewOpen(activeMode === 'interview')
          setInterviewStarted(session.status === 'in_progress')
          if (session.status === 'in_progress') {
            const restored = await listInterviewQuestions(session.id)
            const answered = restored.filter((item) => item.answered)
            const next = restored.find((item) => !item.answered)
            const rebuilt = restored.flatMap((item) => [
              interviewQuestionMessage(item),
              ...(item.answered ? [interviewAnswerMessage(item.question_number, item.answer_text || '')] : []),
            ])
            setInterviewAnswerHistory(answered.map((item) => ({
              question_number: item.question_number,
              question_text: item.question_text || '',
              answer_text: item.answer_text || '',
              score: item.score ?? null,
              feedback: item.feedback ?? null,
            })))
            setInterviewMessages(rebuilt)

            const current = await getInterviewQuestion(session.id).catch(() => null)
            if (!active) return
            if (current) {
              setInterviewQuestion(current)
              setInterviewMessages((currentMessages) => {
                if (currentMessages.some((message) => message.id === interviewMessageId('question', current.question_number))) {
                  return currentMessages
                }
                return [...currentMessages, interviewQuestionMessage(current)]
              })
            } else if (next) {
              setInterviewQuestion(next)
            }
          }
        }
        if (session && session.status === 'completed') {
          setInterviewSession(session)
          setInterviewOpen(activeMode === 'interview')
          setInterviewStarted(false)
          setInterviewReport(session.evaluation_report || null)
        }
      } catch {

      } finally {
        if (active) setInterviewLoading(false)
      }
    }
    if (!interviewRestoreRef.current) {
      interviewRestoreRef.current = true
      restoreInterview()
    } else {
      setInterviewLoading(false)
    }
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
      return undefined
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition
    const instance = new SR()
    instance.lang = 'en-US'
    instance.interimResults = false
    instance.maxAlternatives = 1

    instance.onstart = () => setIsListening(true)
    instance.onend = () => setIsListening(false)
    instance.onerror = (event) => {
      if (event.error === 'not-allowed') {
        setVoiceReplyError('Microphone access denied. Please allow microphone permission.')
      } else {
        setVoiceReplyError('')
      }
    }
    instance.onresult = (event) => {
      const transcript = event.results[0][0].transcript
      setQuestion(transcript.replace(/^\s+|\s+$/g, ''))
    }

    setRecognition(instance)

    return () => {
      instance.stop()
    }
  }, [])

  useEffect(() => {
    return () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
    }
  }, [])

  async function restoreAttachmentScope(sessionId, data, requestId) {
    const items = Array.isArray(data) ? data : []
    const lastGrounded = [...items]
      .reverse()
      .find((item) => item?.role === 'assistant' && Array.isArray(item.sources) && item.sources.length > 0)
    const ids = lastGrounded
      ? [...new Set(lastGrounded.sources.map((source) => source?.document_id).filter(Boolean))]
      : []

    let byId = new Map()
    if (ids.length) {
      try {
        const listed = await listDocuments()
        const documents = Array.isArray(listed) ? listed : listed?.documents || []
        byId = new Map(documents.map((item) => [item.document_id, item]))
      } catch {
      }
      if (messageRequestId.current !== requestId || activeSessionRef.current !== sessionId) return
    }

    const restored = ids
      .filter((id) => byId.size === 0 || byId.has(id))
      .map((id) => {
        const doc = byId.get(id) || {}
        return {
          id: `scope-${id}`,
          documentId: id,
          name: doc.filename || id.slice(0, 8),
          size: doc.byte_size || 0,
          sourceType: doc.source_type || 'knowledge',
          chunkCount: doc.chunk_count ?? null,
          status: 'indexed',
        }
      })

    setDocumentScope(restored)
    setAttachments([])
    setMessages((current) => annotateMessagesWithAttachments(current, byId))
  }

  async function openSession(sessionId) {
    const requestId = ++messageRequestId.current
    activeSessionRef.current = sessionId
    setActiveSessionId(sessionId)
    setActiveMode('chat')
    try { window.sessionStorage.setItem('mitraActiveMode', 'chat') } catch { /* ignore */ }
    setInterviewOpen(false)
    setMessages([])
    setMessagesLoading(true)
    setChatError('')
    setChatNotice('')
    setLastQuestion('')
    setConfirmClearAll(false)
    setAttachments([])
    setDocumentScope([])
    stopSpeaking()

    try {
      const data = await listChatMessages(sessionId)
      if (messageRequestId.current !== requestId) return
      setMessages((Array.isArray(data) ? data : []).map(toChatMessage))
      await restoreAttachmentScope(sessionId, data, requestId)
    } catch (err) {
      if (messageRequestId.current !== requestId) return
      setChatError(err.message)
    } finally {
      if (messageRequestId.current === requestId) setMessagesLoading(false)
    }
  }

  async function handleNewChat() {
    if (creatingSessionRef.current || asking) return

    creatingSessionRef.current = true
    setCreatingSession(true)
    setSessionsError('')
    setChatError('')

    try {
      const session = await createChatSession()
      messageRequestId.current += 1
      activeSessionRef.current = session.id
      setSessions((current) => [session, ...current.filter((item) => item.id !== session.id)])
      setActiveSessionId(session.id)
      setActiveMode('chat')
      try { window.sessionStorage.setItem('mitraActiveMode', 'chat') } catch { /* ignore */ }
      setInterviewOpen(false)
      setMessages([])
      setMessagesLoading(false)
      setChatNotice('')
      setLastQuestion('')
      setConfirmClearAll(false)
      setAttachments([])
      setDocumentScope([])
      stopSpeaking()
    } catch (err) {
      if (err?.status === 429) {
        setChatLimitOpen(true)
        return
      }
      setSessionsError(err.message)
    } finally {
      creatingSessionRef.current = false
      setCreatingSession(false)
    }
  }

  function startRename(session) {
    setRenamingId(session.id)
    setRenameTitle(session.title || '')
    setSessionsError('')
  }

  function cancelRename() {
    setRenamingId(null)
    setRenameTitle('')
  }

  async function handleRename(event, session) {
    event.preventDefault()
    const title = renameTitle.trim()
    if (!title || renaming) return

    setRenaming(true)
    setSessionsError('')
    try {
      const updated = await renameChatSession(session.id, title)
      setSessions((current) =>
        moveSessionToTop(
          current.map((item) => (item.id === updated.id ? updated : item)),
          updated.id,
          updated.updated_at,
        ),
      )
      cancelRename()
    } catch (err) {
      setSessionsError(err.message)
    } finally {
      setRenaming(false)
    }
  }

  async function handleDeleteSession(session) {
    const confirmed = window.confirm(
      `Delete "${session.title || 'this conversation'}"? This conversation and all of its messages will be removed permanently.`,
    )
    if (!confirmed || deletingSessionId) return

    setDeletingSessionId(session.id)
    setSessionsError('')
    try {
      await deleteChatSession(session.id)
      const remaining = sessions.filter((item) => item.id !== session.id)
      setSessions(remaining)

      if (activeSessionRef.current === session.id) {
        messageRequestId.current += 1
        activeSessionRef.current = null
        setActiveSessionId(null)
        setMessages([])
        setMessagesLoading(false)
        setChatError('')
        setChatNotice('')
        setLastQuestion('')
        setConfirmClearAll(false)
        setAttachments([])
        setDocumentScope([])
        stopSpeaking()

        if (remaining[0]) await openSession(remaining[0].id)
      }

      if (renamingId === session.id) cancelRename()
    } catch (err) {
      setSessionsError(err.message)
    } finally {
      setDeletingSessionId(null)
    }
  }

  function handleExportConversation() {
    if (interviewModeActive) {
      if (interviewMessages.length === 0 && !interviewReport) return

      const title = 'Mock Interview Conversation'
      const generatedAt = new Date()
      const candidate = interviewSession?.extracted_info?.candidate_name || interviewSession?.resume_filename || 'Candidate'
      const filename = interviewReportFilename(candidate, generatedAt)
      const html = buildConversationPrintHtml({
        title,
        messages: interviewMessages.filter((message) => !message.failed),
        generatedAt,
      })

      if (!openPrintDocument(html, filename)) {
        setChatNotice('')
        setChatError('The print window was blocked. Allow pop-ups for this site, then try again.')
        return
      }

      setChatError('')
      setChatNotice('Printable interview conversation opened. Choose “Save as PDF” in the print dialog.')
      return
    }

    if (!activeSessionId || messagesLoading) return

    const title = activeSession?.title || 'Conversation'
    const generatedAt = new Date()
    const filename = conversationExportFilename(title, generatedAt)
    const html = buildConversationPrintHtml({
      title,
      messages: messages.filter((message) => !message.failed),
      generatedAt,
    })

    if (!openPrintDocument(html, filename)) {
      setChatNotice('')
      setChatError('The print window was blocked. Allow pop-ups for this site, then try again.')
      return
    }

    setChatError('')
    setChatNotice('Printable conversation opened. Choose “Save as PDF” in the print dialog.')
  }

  async function handleClearHistory() {
    if (clearingHistory) return

    setClearingHistory(true)
    setHistoryError('')
    setHistoryNotice('')

    try {
      const result = await deleteAllChatSessions()
      const deleted =
        result && typeof result.deleted === 'number' ? result.deleted : sessions.length

      messageRequestId.current += 1
      activeSessionRef.current = null
      setSessions([])
      setActiveSessionId(null)
      setMessages([])
      setMessagesLoading(false)
      setChatError('')
      setChatNotice('')
      setLastQuestion('')
      setSessionsError('')
      setConfirmClearAll(false)
      setAttachments([])
      setDocumentScope([])
      cancelRename()
      stopSpeaking()

      setHistoryNotice(
        deleted > 0
          ? `Deleted ${deleted} conversation${deleted === 1 ? '' : 's'} and all of their messages.`
          : 'There was no chat history to delete.',
      )
    } catch (err) {
      setHistoryError(err.message)
    } finally {
      setClearingHistory(false)
    }
  }

  async function uploadAttachment(attachment) {
    setAttachments((current) =>
      current.map((item) =>
        item.id === attachment.id ? { ...item, status: 'uploading', error: null } : item,
      ),
    )
    setUploadingAttachmentId(attachment.id)
    setAttachments((current) =>
      current.map((item) =>
        item.id === attachment.id ? { ...item, status: 'processing' } : item,
      ),
    )
    try {
      const created = await uploadDocument(attachment.file, attachment.sourceType)
      setAttachments((current) =>
        current.map((item) =>
          item.id === attachment.id
            ? {
                ...item,
                status: 'indexed',
                documentId: created.document_id,
                chunkCount: created.chunk_count,
                error: null,
              }
            : item,
        ),
      )
      return created
    } catch (err) {
      setAttachments((current) =>
        current.map((item) =>
          item.id === attachment.id
            ? { ...item, status: 'failed', error: err.message }
            : item,
        ),
      )
      throw err
    } finally {
      setUploadingAttachmentId(null)
    }
  }

  async function retryAttachment(attachment) {
    if (uploadingAttachmentId) return
    setChatError('')
    try {
      await uploadAttachment(attachment)
    } catch (err) {
      setChatError(err.message)
    }
  }

  async function sendQuestion(rawQuestion) {
    const trimmed = rawQuestion.trim()
    if (!trimmed || asking || messagesLoading || creatingSession || !activeSessionId) return

    const sessionId = activeSessionId
    const requestId = messageRequestId.current
    const optimisticId = `local-${Date.now()}-${Math.random()}`
    const controller = new AbortController()
    activeRequestRef.current = controller
    stopRequestedRef.current = false

    setChatError('')
    setChatNotice('')
    setQuestion('')
    setLastQuestion(trimmed)

    const pending = attachments.map((item) => ({ ...item }))
    if (pending.length) {
      setAsking(true)
      try {
        for (const attachment of pending) {
          const target = pending.find((item) => item.id === attachment.id)
          if (!target || target.status === 'indexed') continue

          const created = await uploadAttachment(target)
          target.status = 'indexed'
          target.documentId = created.document_id
          target.chunkCount = created.chunk_count
          target.name = created.filename || target.name
          target.size = created.byte_size || target.size
          target.sourceType = created.source_type || target.sourceType
        }
      } catch (err) {
        if (controller.signal.aborted) return
        if (messageRequestId.current !== requestId || activeSessionRef.current !== sessionId) return
        setChatError(err.message)
        setAsking(false)
        return
      }
    }

    if (controller.signal.aborted) return

    const sentAttachments = pending
      .filter((item) => item.status === 'indexed' && item.documentId)
      .map(toMessageAttachment)
    const nextScope = mergeScope(documentScope, sentAttachments)
    setDocumentScope(nextScope)
    setAttachments([])
    const indexedDocumentIds = nextScope.map((item) => item.documentId)

    setMessages((current) => [
      ...current.filter((message) => !message.failed),
      {
        id: optimisticId,
        role: 'user',
        text: trimmed,
        time: nowLabel(),
        attachments: sentAttachments,
      },
    ])
    setAsking(true)

    if (GREETING_PATTERN.test(trimmed)) {
      setMessages((current) => [
        ...current,
        {
          id: `${optimisticId}-reply`,
          role: 'assistant',
          text: GREETING_REPLY,
          sources: [],
          hasEvidence: true,
          time: nowLabel(),
        },
      ])
      setAsking(false)
      return
    }

    const jobContext = jobContextFromMessages(messages)
    const jobOptions = {}
    if (jobContext.preferences) {
      const { kind, ...preferences } = jobContext.preferences
      jobOptions.jobPreferences = preferences
    }
    if (jobContext.awaitingResponse && trimmed.length < 80 && !trimmed.includes('?')) {
      jobOptions.jobSearch = true
    }

    try {
      const exchange = await sendChatMessage(sessionId, trimmed, {
        documentIds: indexedDocumentIds,
        signal: controller.signal,
        ...jobOptions,
      })
      if (messageRequestId.current !== requestId || activeSessionRef.current !== sessionId) {
        return
      }

      setMessages((current) => {
        const optimistic = current.find((message) => message.id === optimisticId)
        const persisted = toChatMessage(exchange.user_message)
        return [
          ...current.filter((message) => message.id !== optimisticId),
          { ...persisted, attachments: optimistic?.attachments || [] },
          toChatMessage(exchange.assistant_message),
        ]
      })
      setSessions((current) => moveSessionToTop(current, sessionId))
    } catch (err) {
      if (controller.signal.aborted || err?.aborted) {
        if (!stopRequestedRef.current) setChatError('The request timed out. Please try again.')
        return
      }
      if (messageRequestId.current !== requestId || activeSessionRef.current !== sessionId) {
        return
      }

      setMessages((current) =>
        current.map((message) => (message.id === optimisticId ? { ...message, failed: true } : message)),
      )
      setChatError(err.message)
    } finally {
      if (activeRequestRef.current === controller) activeRequestRef.current = null
      setAsking(false)
    }
  }

  function handleStop() {
    const controller = activeRequestRef.current
    if (!controller) return
    stopRequestedRef.current = true
    controller.abort()
    activeRequestRef.current = null
    stopSpeaking()
    setAsking(false)
  }

  async function handleAsk(event) {
    event.preventDefault()
    if (interviewModeActive) {
      const answer = question.trim()
      if (!answer || interviewSubmitting || !interviewQuestion || interviewSession?.status !== 'in_progress') return
      setQuestion('')
      await submitInterviewChatAnswer(answer)
      return
    }
    await sendQuestion(question)
  }

  function handleChatKeyDown(event) {
    if (event.key !== 'Enter') return
    if (event.shiftKey) return
    event.preventDefault()
    handleAsk(event)
  }

  function handleRetry() {
    if (!lastQuestion || asking || messagesLoading) return
    setMessages((current) => current.filter((message) => !message.failed))
    sendQuestion(lastQuestion)
  }

  const speakMessage = (messageId, text) => {
    if (!window.speechSynthesis || !text?.trim()) return
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'en-US'
    utterance.rate = 1
    utterance.pitch = 1
    utterance.onstart = () => {
      setIsSpeaking(true)
      setSpeakingMessageId(messageId)
    }
    utterance.onend = () => {
      setIsSpeaking(false)
      setSpeakingMessageId(null)
    }
    utterance.onerror = (event) => {
      setIsSpeaking(false)
      setSpeakingMessageId(null)
      if (event.error) {
        setVoiceReplyError(`Speech playback error: ${event.error}`)
      }
    }
    window.speechSynthesis.speak(utterance)
    speechUtteranceRef.current = utterance
  }

  function stopSpeaking() {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    setIsSpeaking(false)
    setSpeakingMessageId(null)
  }

  function handleMicClick() {
    if (!activeSessionId || asking || messagesLoading) return
    if (!recognition) {
      setVoiceReplyError('Speech recognition is not supported in this browser. Type your question instead.')
      return
    }
    if (isListening) {
      recognition.stop()
      setIsListening(false)
    } else {
      recognition.start()
      setIsListening(true)
    }
  }

  function handleSpeakClick(messageId, text) {
    if (isSpeaking && speakingMessageId === messageId) {
      stopSpeaking()
    } else {
      speakMessage(messageId, text)
    }
  }

  async function startInterviewFlow() {
    if (interviewFlowRef.current) return
    interviewFlowRef.current = true
    setInterviewError('')
    setActiveMode('interview')
    try { window.sessionStorage.setItem('mitraActiveMode', 'interview') } catch { /* ignore */ }
    setInterviewOpen(true)
    setQuestion('')
    setInterviewStarted(false)
    try {
      let session = interviewSession
      if (!session || session.status === 'completed') {
        const current = await getCurrentInterviewSession()
        session = current && current.status !== 'completed' ? current : null
        if (!session) session = await createInterviewSession()
      }
      setInterviewSession(session)
      setInterviewStarted(session.status === 'in_progress')
      if (session.status === 'in_progress') {
        await refreshInterviewQuestion(session.id)
      }
    } catch (err) {
      setInterviewError(err.message || 'Could not start the interview setup.')
    } finally {
      interviewFlowRef.current = false
    }
  }

  function openInterviewFilePicker() {
    if (interviewUploading) return
    setInterviewError('')
    interviewFileInputRef.current?.click()
  }

  function handleReplaceResume() {
    if (interviewUploading) return
    if (interviewSession?.status === 'in_progress') {
      const confirmed = window.confirm(
        'Replacing the resume will reset the current interview questions and answers. Do you want to continue?',
      )
      if (!confirmed) return
    }
    openInterviewFilePicker()
  }

  async function handleRemoveInterviewResume() {
    if (!interviewSession?.id || interviewUploading) return
    const confirmed = window.confirm(
      'Are you sure you want to remove this resume from your interview?',
    )
    if (!confirmed) return
    setInterviewMessages([])
    setInterviewError('')
    try {
      const updated = await deleteInterviewResume(interviewSession.id)
      setInterviewSession(updated)
      setInterviewStarted(false)
      setInterviewQuestion(null)
      setInterviewAnswerHistory([])
      setInterviewReport(null)
      setInterviewFileName('')
    } catch (err) {
      setInterviewError(err.message || 'Could not remove the resume. Please try again.')
    }
  }

  async function handleInterviewFileChange(event) {
    const file = event.target.files && event.target.files[0]
    event.target.value = ''
    if (!file) return

    const ext = `.${String(file.name || '').split('.').pop().toLowerCase()}`
    if (!INTERVIEW_ACCEPTED_EXTENSIONS.includes(ext)) {
      setInterviewError('Unsupported file type. Please upload a PDF or DOCX resume.')
      return
    }
    if (file.size === 0) {
      setInterviewError('That file is empty. Please upload a readable resume.')
      return
    }
    if (file.size > INTERVIEW_MAX_UPLOAD_BYTES) {
      setInterviewError(`That file is ${formatBytes(file.size)}. The limit is ${formatBytes(INTERVIEW_MAX_UPLOAD_BYTES)}.`)
      return
    }

    let session = interviewSession
    try {
      if (!session || session.status === 'completed') {
        session = await createInterviewSession()
        setInterviewSession(session)
      }
    } catch (err) {
      setInterviewError(err.message || 'Could not create an interview session.')
      return
    }

    setInterviewUploading(true)
    setInterviewUploadPhase('Uploading resume...')
    setInterviewError('')
    setInterviewFileName(file.name)
    const phaseTimer = window.setInterval(() => {
      setInterviewUploadPhase((current) => {
        if (current === 'Uploading resume...') return 'Extracting resume content...'
        if (current === 'Extracting resume content...') return 'Analyzing candidate profile...'
        return current
      })
    }, 900)
    try {
      const updated = await uploadInterviewResume(session.id, file)
      setInterviewSession(updated)
      setInterviewStarted(updated.status === 'in_progress')
      setInterviewQuestion(null)
      setInterviewAnswerHistory([])
      setInterviewReport(null)
      setInterviewUploadPhase('Interview ready')
    } catch (err) {
      setInterviewError(err.message || 'Could not process the resume. Please try a different file.')
    } finally {
      window.clearInterval(phaseTimer)
      setInterviewUploading(false)
    }
  }

  async function handleStartInterview() {
    if (!interviewSession?.id || interviewSession.status !== 'ready' || interviewStarting) return
    if (interviewStartRef.current) return
    interviewStartRef.current = true
    setInterviewStarting(true)
    setInterviewError('')
    setInterviewStartError('')
    const controller = new AbortController()
    const timeout = window.setTimeout(() => controller.abort(), 90000)
    try {
      const result = await startInterviewSession(interviewSession.id, { signal: controller.signal })
      const session = result?.session || result
      const questions = Array.isArray(result?.questions) ? result.questions : []
      setInterviewSession(session)
      setInterviewStarted(true)
      if (session.status === 'in_progress') {
        const candidate = session.extracted_info?.candidate_name || 'there'
        setInterviewMessages((current) => [
          ...current.filter((message) => !String(message.id || '').startsWith('interview-')),
          {
            id: 'interview-welcome',
            role: 'assistant',
            text: `Welcome, ${candidate}! I have reviewed your resume. Let's begin your interview.`,
            time: nowLabel(),
            sources: [],
            hasEvidence: true,
          },
        ])
        const currentNumber = Number(session.current_question_number) || 1
        const current =
          questions.find((item) => Number(item.question_number) === currentNumber)
          || questions.find((item) => !item.answered)
          || questions[0]
          || null
        if (current) {
          setInterviewQuestion(current)
          setInterviewMessages((currentMessages) => [
            ...currentMessages.filter((message) => message.id !== interviewMessageId('question', current.question_number)),
            interviewQuestionMessage(current),
          ])
        } else {
          await refreshInterviewQuestion(session.id)
        }
      }
    } catch (err) {
      const message = err?.name === 'AbortError'
        ? 'Starting the interview took too long. Please retry.'
        : (err.message || 'Could not start the interview session.')
      setInterviewError(message)
      setInterviewStartError(message)
     
      try {
        const current = await getCurrentInterviewSession()
        if (current && current.id === interviewSession.id && current.status === 'in_progress') {
          setInterviewSession(current)
          setInterviewStarted(true)
          await refreshInterviewQuestion(current.id)
          setInterviewError('')
          setInterviewStartError('')
        }
      } catch {

      }
    } finally {
      window.clearTimeout(timeout)
      interviewStartRef.current = false
      setInterviewStarting(false)
    }
  }

  async function handleRetryNextQuestion() {
    if (!interviewSession?.id || interviewNextLoading) return
    setInterviewNextLoading(true)
    setInterviewError('')
    try {
      await refreshInterviewQuestion(interviewSession.id)
    } finally {
      setInterviewNextLoading(false)
    }
  }

  async function refreshInterviewQuestion(sessionId) {
    try {
      const question = await getInterviewQuestion(sessionId)
      if (!question) return null
      setInterviewError('')
      setInterviewQuestion(question)
      setInterviewMessages((current) => {
        if (current.some((message) => message.id === interviewMessageId('question', question.question_number))) return current
        return [...current, interviewQuestionMessage(question)]
      })
      return question
    } catch (err) {
      setInterviewError(err.message || 'Could not load the interview question.')
      return null
    }
  }

  async function submitInterviewChatAnswer(answer) {
    if (!interviewSession?.id || !interviewQuestion || interviewSubmitting) return false
    if (interviewSubmitRef.current) return false
    interviewSubmitRef.current = true
    const number = interviewQuestion.question_number
    setInterviewSubmitting(true)
    setInterviewMessages((current) => [
      ...current.filter((message) => message.id !== interviewMessageId('answer', number)),
      interviewAnswerMessage(number, answer),
    ])
    try {
      const result = await submitInterviewAnswer(interviewSession.id, number, answer)
      setInterviewAnswerHistory((current) => [
        ...current.filter((item) => item.question_number !== number),
        {
          question_number: number,
          question_text: interviewQuestion.question_text || '',
          answer_text: answer,
          score: result?.question?.score ?? null,
          feedback: result?.question?.feedback ?? null,
          evaluation: result?.evaluation ?? null,
        },
      ])
      if (result?.advanced) {
        if (result?.next_question_ready === false) {
          setInterviewError('Your answer was saved. The next question is still being prepared — please retry.')
          return true
        }
        const next = await refreshInterviewQuestion(interviewSession.id)
        if (!next) {
          setInterviewError('Your answer was saved, but the next question could not be loaded. Retry to continue.')
        }
        return true
      }
      setInterviewCompleting(true)
      try {
        const report = await completeInterviewSession(interviewSession.id)
        setInterviewReport(report)
        setInterviewSession((current) => current && { ...current, status: 'completed', final_score: report?.score, evaluation_report: report })
        setInterviewMessages((current) => [
          ...current,
          {
            id: 'interview-complete',
            role: 'assistant',
            text: `Your interview is complete! I have evaluated your responses.\n\n${String(report?.summary || `Overall score: ${report?.score ?? 0}/10 (${report?.level || 'Needs Improvement'})`)}`,
            time: nowLabel(),
            sources: [],
            hasEvidence: true,
          },
        ])
      } finally {
        setInterviewCompleting(false)
      }
      return true
    } catch (err) {
      setInterviewError(err.message || 'Could not submit the answer.')
      setInterviewMessages((current) => current.filter((message) => message.id !== interviewMessageId('answer', number)))
      setQuestion(answer)
      return false
    } finally {
      interviewSubmitRef.current = false
      setInterviewSubmitting(false)
    }
  }

  async function handleStartNewInterview() {
    setInterviewMessages([])
    setInterviewError('')
    setInterviewStartError('')
    setInterviewStarted(false)
    setInterviewQuestion(null)
    setInterviewAnswerHistory([])
    setInterviewReport(null)
    try {
      const session = await createInterviewSession()
      setInterviewSession(session)
      setInterviewOpen(true)
    } catch (err) {
      setInterviewError(err.message || 'Could not start a new interview.')
    }
  }

  async function handleExportInterviewReport() {
    if (!interviewReport) return
    setInterviewReportExporting(true)
    try {
      const candidateName = interviewSession?.extracted_info?.candidate_name || interviewSession?.resume_filename || ''
      const generatedAt = interviewReport.completed_at || new Date().toISOString()
      const html = buildInterviewPrintHtml({
        report: interviewReport,
        candidateName,
        resumeFilename: interviewSession?.resume_filename || '',
        generatedAt,
      })
      const opened = openPrintDocument(html, interviewReportFilename(candidateName, generatedAt))
      if (!opened) {
        setInterviewError('The print window was blocked. Allow pop-ups for this site, then try again.')
      }
    } finally {
      setInterviewReportExporting(false)
    }
  }

  function closeInterviewSetup() {
    setInterviewOpen(false)
    setActiveMode('chat')
    try { window.sessionStorage.setItem('mitraActiveMode', 'chat') } catch { /* ignore */ }
    setInterviewError('')
    setInterviewFileName('')
  }

  function openFilePicker() {
    if (uploadingAttachmentId) return
    fileInputRef.current?.click()
  }

  function handleFileChange(event) {
    const files = Array.from(event.target.files || [])
    event.target.value = ''
    files.forEach((file) => {
      const problem = validateFile(file)
      if (problem) {
        setUploadError(problem)
        return
      }
      setUploadError('')
      setAttachments((current) => [
        ...current,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          file,
          name: file.name,
          size: file.size,
          sourceType: sourceTypeForFile(file.name),
          status: 'ready',
          documentId: null,
          chunkCount: null,
          error: null,
        },
      ])
    })
  }

  function removeAttachment(attachmentId) {
    setAttachments((current) => current.filter((item) => item.id !== attachmentId))
  }

  const emptySession = !messagesLoading && messages.length === 0

  // Interview is a dedicated conversation, separate from the normal chat session.
  // The mode is explicit so chat and interview never share message state or IDs.
  const interviewModeActive = recruiterMode && activeMode === 'interview'
  const greetingReply = recruiterMode ? GREETING_REPLY : CANDIDATE_GREETING_REPLY
  const suggestions = recruiterMode ? SUGGESTED_QUESTIONS : CANDIDATE_SUGGESTED_QUESTIONS
  const visibleMessages = interviewModeActive ? interviewMessages : messages

  return (
    <div className="page np np-assistant">
      <header className="page-header">
        <div>
          <h1 className="page-title">Mitra Assistant</h1>
          <p className="page-sub">{recruiterMode
            ? 'Ask anything about your jobs, candidates, or recruitment workflow.'
            : 'Ask anything about your resume, skills, career growth, applications, or interviews.'}</p>
        </div>
      </header>

      {historyOpen && <div className="as-drawer-overlay" onClick={() => setHistoryOpen(false)} />}
      {teamOpen && <div className="as-drawer-overlay" onClick={() => setTeamOpen(false)} />}

      <div className="as-layout">
        <nav className="card as-history" aria-label="Chat history">
          <button
            type="button"
            className="btn btn-primary btn-block as-new-chat"
            onClick={handleNewChat}
            disabled={creatingSession || asking}
          >
            <NwIcon name="plus" /> {creatingSession ? 'Creating…' : 'New chat'}
          </button>

          {sessionsLoading && <p className="muted" style={{ fontSize: 12.5 }}>Loading conversations…</p>}
          {sessionsError && (
            <p className="muted" style={{ fontSize: 12.5, color: 'var(--danger)' }}>{sessionsError}</p>
          )}
          {!sessionsLoading && !sessionsError && groups.length === 0 && (
            <p className="muted" style={{ fontSize: 12.5 }}>No conversations yet. Start a new chat.</p>
          )}
          {groups.map((group) => (
            <div key={group.name}>
              <div className="eyebrow">{group.name}</div>
              <ul>
                {group.items.map((session) => (
                  <li key={session.id} className="as-session">
                    {renamingId === session.id ? (
                      <form className="as-rename" onSubmit={(event) => handleRename(event, session)}>
                        <input
                          className="input"
                          value={renameTitle}
                          onChange={(event) => setRenameTitle(event.target.value)}
                          aria-label="Conversation title"
                          autoFocus
                        />
                        <div className="as-rename-actions">
                          <button type="submit" className="link" disabled={renaming}>Save</button>
                          <button type="button" className="link" onClick={cancelRename}>Cancel</button>
                        </div>
                      </form>
                    ) : (
                      <>
                        <button
                          type="button"
                          className={session.id === activeSessionId ? 'active' : ''}
                          aria-current={session.id === activeSessionId}
                          onClick={() => openSession(session.id)}
                        >
                          <span className="as-session-title">{session.title || 'New chat'}</span>
                          <small>{sessionTimeLabel(session.updated_at)}</small>
                        </button>
                        <span className="as-session-actions">
                          <button type="button" aria-label={`Rename ${session.title || 'conversation'}`} onClick={() => startRename(session)}>
                            <PencilIcon />
                          </button>
                          <button
                            type="button"
                            aria-label={`Delete ${session.title || 'conversation'}`}
                            disabled={deletingSessionId === session.id}
                            onClick={() => handleDeleteSession(session)}
                          >
                            <TrashIcon />
                          </button>
                        </span>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div className="as-history-foot">
            <button type="button" className={`link as-interview-entry${interviewModeActive ? ' active' : ''}`} onClick={startInterviewFlow} aria-current={interviewModeActive ? 'page' : undefined}>
              <NwIcon name="briefcase-business" /> Interview
            </button>
            <button type="button" className="link as-export" onClick={handleExportConversation} disabled={interviewModeActive
              ? (interviewMessages.length === 0 && !interviewReport)
              : (!activeSessionId || messagesLoading)}>
              {interviewModeActive ? 'Export interview (PDF)' : 'Export chat (PDF)'}
            </button>
            {confirmClearAll ? (
              <span className="as-confirm-clear">
                Delete all conversations?
                <button type="button" className="link" style={{ color: 'var(--danger)' }} onClick={handleClearHistory} disabled={clearingHistory}>
                  {clearingHistory ? 'Deleting…' : 'Yes, delete'}
                </button>
                <button type="button" className="link" onClick={() => setConfirmClearAll(false)}>Cancel</button>
              </span>
            ) : (
              <button type="button" className="link" style={{ color: 'var(--danger)' }} onClick={() => setConfirmClearAll(true)} disabled={sessions.length === 0}>
                Clear all history
              </button>
            )}
          </div>

          {(historyNotice || historyError) && (
            <p className="muted" style={{ fontSize: 11.5, color: historyError ? 'var(--danger)' : undefined }}>
              {historyError || historyNotice}
            </p>
          )}
        </nav>

        <section className="card as-chat" aria-label="Conversation">
          <div className="as-chat-head">
            <span className="as-chat-icon"><NwIcon name="sparkle" /></span>
            <div>
              <strong>{interviewModeActive ? 'AI Mock Interview' : (activeSession ? activeSession.title || 'New chat' : 'Mitra Assistant')}</strong>
              <small className="muted">{interviewModeActive
                ? (interviewSession?.status === 'in_progress'
                  ? (interviewQuestion
                    ? `Interview Progress: Question ${interviewQuestion.question_number} of ${interviewQuestion.total_questions || interviewSession.total_questions || 10}`
                    : 'Interview Progress: preparing your question…')
                  : interviewSession?.status === 'completed'
                    ? 'Interview complete · Final report'
                    : 'Interview setup · Resume-based interview')
                : (recruiterMode ? 'Recruiter Support agent' : 'Candidate Support agent')}</small>
            </div>
            <div className="as-chat-head-actions">
              <button type="button" className="as-icon-btn as-history-toggle" onClick={() => setHistoryOpen(true)} aria-label="Open chat history" title="Chat history">
                <NwIcon name="list" />
              </button>
              <button type="button" className="as-icon-btn as-team-toggle" onClick={() => setTeamOpen(true)} aria-label="Open AI team" title="Your AI team">
                <NwIcon name="users" />
              </button>
            </div>
          </div>

          {(chatError || chatNotice || voiceReplyError || uploadError) && (
            <p
              className="as-note"
              style={{ color: chatError || voiceReplyError || uploadError ? 'var(--danger)' : undefined }}
            >
              {chatError || voiceReplyError || uploadError || chatNotice}
              {chatError && (
                <>
                  {' '}
                  <button type="button" className="link" onClick={handleRetry}>Retry</button>
                </>
              )}
            </p>
          )}

          <div className="as-messages" ref={messagesRef} role="log" aria-live="polite">
            {recruiterMode && interviewOpen && (
              <div className="as-interview-panel card">
                <div className="as-interview-head">
                  <span className="as-interview-icon"><NwIcon name="briefcase-business" /></span>
                  <div><strong>AI Mock Interview</strong><small className="muted">Resume-based interview setup</small></div>
                  <button type="button" className="as-icon-btn" onClick={closeInterviewSetup} aria-label="Close interview setup"><NwIcon name="x" /></button>
                </div>
                <div className="as-interview-body">
                  <p>{INTERVIEW_WELCOME}</p>
                  <input ref={interviewFileInputRef} type="file" accept={INTERVIEW_ACCEPTED_EXTENSIONS.join(',')} className="sr-only" onChange={handleInterviewFileChange} tabIndex={-1} aria-hidden="true" />
                  {interviewError && <p className="as-interview-error" role="alert">{interviewError}</p>}
                  {interviewSession?.status === 'in_progress' && !interviewQuestion && (
                    <p className="as-interview-error" role="alert">
                      The next question is being prepared.{' '}
                      <button type="button" className="link" onClick={handleRetryNextQuestion} disabled={interviewNextLoading}>
                        {interviewNextLoading ? 'Retrying...' : 'Retry'}
                      </button>
                    </p>
                  )}
                  {(!interviewSession || interviewSession.status === 'awaiting_resume') && !interviewStarted && interviewSession?.status !== 'ready' && (
                    <div className="as-interview-upload">
                      <button type="button" className="btn btn-secondary" onClick={openInterviewFilePicker} disabled={interviewUploading || interviewLoading}><NwIcon name="upload" /> {interviewUploading ? (interviewUploadPhase || 'Processing...') : 'Upload resume'}</button>
                      <small className="muted">Accepted formats: PDF, DOCX. Maximum size: {formatBytes(INTERVIEW_MAX_UPLOAD_BYTES)}.</small>
                      {interviewFileName && <p className="muted">File: {interviewFileName}</p>}
                      {interviewUploading && <p className="muted">{interviewUploadPhase || 'Uploading and processing resume...'}</p>}
                    </div>
                  )}
                  {interviewSession && (
                    <div className="as-interview-status">
                      <p><strong>Resume:</strong> {interviewSession.resume_filename || 'Not uploaded yet'}</p>
                      <p><strong>Status:</strong> {interviewUploading ? (interviewUploadPhase || 'Processing...') : interviewSession.status === 'ready' ? 'Indexed / Ready' : interviewSession.status === 'in_progress' ? 'Interview started' : interviewSession.status === 'awaiting_resume' ? 'Awaiting resume' : interviewSession.status}</p>
                      {interviewSession.resume_filename && !interviewUploading && interviewSession.status !== 'completed' && (
                        <div className="as-interview-resume-actions">
                          <button type="button" className="link as-replace-resume" onClick={handleReplaceResume}>
                            <NwIcon name="refresh-cw" /> Replace Resume
                          </button>
                          {interviewSession.status !== 'in_progress' && (
                            <button type="button" className="link as-remove-resume" onClick={handleRemoveInterviewResume}>
                              <NwIcon name="trash-2" /> Delete Resume
                            </button>
                          )}
                        </div>
                      )}
                      {interviewUploading && <p className="muted">{interviewUploadPhase || 'Processing resume...'}</p>}
                    </div>
                  )}
                  {resumeSummary && (
                    <div className="as-interview-summary">
                      <h4>Resume Analysis Complete</h4>
                      <ul>
                        {resumeSummary.candidate && <li><strong>Candidate:</strong> {resumeSummary.candidate}</li>}
                        {resumeSummary.role && <li><strong>Role:</strong> {resumeSummary.role}</li>}
                        {resumeSummary.experience && <li><strong>Experience:</strong> {resumeSummary.experience}</li>}
                        {resumeSummary.location && <li><strong>Location:</strong> {resumeSummary.location}</li>}
                        {resumeSummary.skills.length > 0 && <li><strong>Key Skills:</strong> {resumeSummary.skills.join(', ')}.</li>}
                        {resumeSummary.summary && <li><strong>Experience Summary:</strong> {resumeSummary.summary}</li>}
                      </ul>
                      {resumeSummary.projects.length > 0 && (
                        <div className="as-interview-summary-projects">
                          <strong>Relevant Projects:</strong>
                          <ul>{resumeSummary.projects.map((project, index) => <li key={`project-${index}`}>{project}</li>)}</ul>
                        </div>
                      )}
                    </div>
                  )}
                  {interviewSession?.status === 'ready' && !interviewStarted && !interviewUploading && (
                    <div className="as-interview-ready">
                      <p><strong>Your resume has been analysed. You are ready to start your mock interview.</strong></p>
                      <div className="as-interview-defaults">
                        <p><strong>Interview type:</strong> {interviewSession.interview_type || INTERVIEW_DEFAULTS.interview_type}</p>
                        <p><strong>Total questions:</strong> {interviewSession.total_questions || INTERVIEW_DEFAULTS.total_questions}</p>
                        <p><strong>Difficulty:</strong> {interviewSession.difficulty || INTERVIEW_DEFAULTS.difficulty} ({INTERVIEW_DIFFICULTY_PROGRESSION})</p>
                        <p><strong>Mode:</strong> {interviewSession.mode || INTERVIEW_DEFAULTS.mode}</p>
                      </div>
                      <button type="button" className="btn btn-primary" onClick={handleStartInterview} disabled={interviewStarting}>{interviewStarting ? 'Starting interview...' : interviewStartError ? 'Retry Start Interview' : 'Start Interview'}</button>
                    </div>
                  )}
                  {interviewReport && interviewSession?.status === 'completed' && (
                    <div className="as-interview-report">
                      <div className="as-interview-report-score">
                        <strong>{interviewReport.score ?? 0}</strong>
                        <span>/ 10</span>
                        <small>{interviewReport.level || 'Needs Improvement'}</small>
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Overall performance</h4>
                        <p>{interviewReport.questions_answered ?? 0} of {interviewReport.questions_total ?? 10} questions completed.</p>
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Category-wise score</h4>
                        {(Object.keys(interviewReport.category_scores || {}) || []).map((key) => (
                          <div className="as-interview-report-category" key={key}>
                            <span>{String(key).replace(/_/g, ' ')}</span>
                            <div className="as-interview-progress"><div className="as-interview-progress-bar" style={{ width: `${interviewReport.category_scores[key]}%` }} /></div>
                            <span>{interviewReport.category_scores[key]}</span>
                          </div>
                        ))}
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Strengths</h4>
                        <ul>
                          {(interviewReport.strengths || []).map((item, index) => <li key={`interview-strength-${index}`}>{item}</li>)}
                        </ul>
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Areas for improvement</h4>
                        <ul>
                          {(interviewReport.areas_for_improvement || []).map((item, index) => <li key={`interview-area-${index}`}>{item}</li>)}
                        </ul>
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Answered questions feedback</h4>
                        {(interviewReport.answered_questions || []).map((item) => (
                          <div className="as-interview-report-question" key={`interview-answer-${item.question_number}`}>
                            <p><strong>Q{Number(item.question_number || 0)}:</strong> {item.question_text}</p>
                            <p><strong>Score:</strong> {item.score ?? '—'}/10</p>
                            {item.feedback?.what_went_well && <p><strong>Well answered:</strong> {item.feedback.what_went_well}</p>}
                            {(item.feedback?.improvements || []).map((improvement, index) => <p key={`interview-answer-${item.question_number}-improvement-${index}`}><strong>Improvement:</strong> {improvement}</p>)}
                            {(item.feedback?.missing_points || []).map((missing, index) => <p key={`interview-answer-${item.question_number}-missing-${index}`}><strong>Missing:</strong> {missing}</p>)}
                          </div>
                        ))}
                      </div>
                      <div className="as-interview-report-section">
                        <h4>Recommendations</h4>
                        <ul>
                          {(interviewReport.recommendations || []).map((item, index) => <li key={`interview-recommendation-${index}`}>{item}</li>)}
                        </ul>
                      </div>
                      <div className="as-interview-report-actions">
                        <button type="button" className="btn btn-secondary" onClick={handleExportInterviewReport} disabled={interviewReportExporting}>
                          {interviewReportExporting ? 'Preparing PDF...' : 'Download Interview Report (PDF)'}
                        </button>
                        <button type="button" className="btn btn-primary" onClick={handleStartNewInterview}>Start New Interview</button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {!interviewModeActive && messagesLoading && <p className="muted as-state">Loading conversation.</p>}

            {!interviewModeActive && !messagesLoading && !activeSessionId && (
              <div className="as-state-card">
                <NwIcon name="sparkle" />
                <h2>Start a conversation</h2>
                <p className="muted">Create a new chat and ask Mitra about your candidates, jobs or documents.</p>
                <button type="button" className="btn btn-primary" onClick={handleNewChat} disabled={creatingSession}>
                  <NwIcon name="plus" /> New chat
                </button>
              </div>
            )}

            {!interviewModeActive && emptySession && activeSessionId && (
              <div className="as-row">
                <span className="as-bot" aria-hidden="true"><NwIcon name="sparkle" /></span>
                <div className="as-bubble bot">
                  <p>{greetingReply}</p>
                </div>
              </div>
            )}

            {(interviewModeActive
              ? visibleMessages
              : messages
            ).map((message) =>
              message.role === 'user' ? (
                <div key={message.id} className="as-row user">
                  <div className="as-row-stack">
                    <div className="as-bubble user">
                      {Array.isArray(message.attachments) && message.attachments.length > 0 && (
                        <div className="as-message-attachments">
                          {message.attachments.map((attachment) => (
                            <div className="as-message-attachment" key={attachment.id || attachment.documentId}>
                              <NwIcon name="file" />
                              <span className="as-message-attachment-main">
                                <strong title={attachment.name}>{attachment.name}</strong>
                                <small>
                                  {SOURCE_LABELS[attachment.sourceType] || attachment.sourceType || 'Document'}
                                  {attachment.size > 0 ? ` · ${formatBytes(attachment.size)}` : ''}
                                  {attachment.chunkCount ? ` · ${attachment.chunkCount} chunks` : ''}
                                </small>
                              </span>
                              <small className="as-attachment-status">Indexed</small>
                            </div>
                          ))}
                        </div>
                      )}
                      <span className="as-text">{message.text}</span>
                      {message.failed && (
                        <>
                          {' '}
                          <button type="button" className="as-retry" onClick={handleRetry}>Retry</button>
                        </>
                      )}
                    </div>
                    <small className="as-time">{message.time}</small>
                  </div>
                </div>
              ) : (
                <div key={message.id} className="as-row">
                  <span className="as-bot" aria-hidden="true"><NwIcon name="sparkle" /></span>
                  <div className={`as-bubble bot${String(message.id || '').startsWith('interview-') ? ' as-interview-text' : ''}`}>
                    <p>{message.text}</p>
                    {messageSources(message)}
                    <div className="as-bubble-foot">
                      <button
                        type="button"
                        className={`as-speak ${isSpeaking && speakingMessageId === message.id ? 'speaking' : ''}`}
                        onClick={() => handleSpeakClick(message.id, message.text)}
                        aria-label={isSpeaking && speakingMessageId === message.id ? 'Stop reading aloud' : 'Read answer aloud'}
                      >
                        {isSpeaking && speakingMessageId === message.id ? <StopSpeakerIcon /> : <SpeakerIcon />}
                        {isSpeaking && speakingMessageId === message.id ? 'Stop' : 'Listen'}
                      </button>
                      <small className="as-time">{message.time}</small>
                    </div>
                  </div>
                </div>
              ),
            )}

            {!interviewModeActive && asking && (
              <div className="as-row">
                <span className="as-bot" aria-hidden="true"><NwIcon name="sparkle" /></span>
                <p className="as-bubble bot as-typing" aria-label="Mitra is thinking"><i /><i /><i /></p>
              </div>
            )}
          </div>

          <div className="as-suggest" aria-label="Suggested questions" hidden={interviewModeActive}>
            {suggestions.map((suggestion) => (
              <button key={suggestion} type="button" disabled={asking || !activeSessionId} onClick={() => sendQuestion(suggestion)}>
                <NwIcon name="sparkle" /> {suggestion}
              </button>
            ))}
          </div>

          <form className="as-composer" onSubmit={handleAsk}>
            {!interviewModeActive && attachments.length > 0 && (
              <div className="as-attachment-list">
                {attachments.map((attachment) => (
                  <div key={attachment.id} className="as-attachment">
                    <NwIcon name="file" />
                    <span className="as-attachment-main">
                      <strong title={attachment.name}>{attachment.name}</strong>
                      <small className="muted">
                        {formatBytes(attachment.size)} · {SOURCE_LABELS[attachment.sourceType] || attachment.sourceType}
                      </small>
                    </span>
                    {attachment.status === 'uploading' && (
                      <small className="muted">Uploading…</small>
                    )}
                    {attachment.status === 'processing' && (
                      <small className="muted">Processing &amp; indexing…</small>
                    )}
                    {attachment.status === 'indexed' && (
                      <small className="muted">
                        Indexed{attachment.chunkCount ? ` · ${attachment.chunkCount} chunks` : ''}
                      </small>
                    )}
                    {attachment.status === 'failed' && (
                      <>
                        <small style={{ color: 'var(--danger)' }} title={attachment.error || 'Upload failed'}>
                          Failed
                        </small>
                        <button
                          type="button"
                          className="link"
                          onClick={() => retryAttachment(attachment)}
                          disabled={Boolean(uploadingAttachmentId)}
                          title="Retry upload"
                        >
                          Retry
                        </button>
                      </>
                    )}
                    {(!attachment.status || attachment.status === 'ready' || attachment.status === 'failed') && (
                      <button
                        type="button"
                        className="as-attachment-remove"
                        onClick={() => removeAttachment(attachment.id)}
                        aria-label={`Remove ${attachment.name}`}
                        title="Remove attachment"
                      >
                        <NwIcon name="x" />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            <div className="as-composer-row">
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_EXTENSIONS.join(',')}
                className="sr-only"
                onChange={handleFileChange}
                tabIndex={-1}
                aria-hidden="true"
              />
              <button
                type="button"
                className="as-attach"
                onClick={openFilePicker}
                disabled={Boolean(uploadingAttachmentId)}
                aria-label="Attach document"
                title="Attach document"
              >
                <NwIcon name="paperclip" />
              </button>
              <div className="as-input">
                <textarea
                  id="as-text"
                  ref={textareaRef}
                  rows={1}
                  placeholder={interviewModeActive
                    ? (interviewSession?.status === 'in_progress'
                      ? 'Type your interview answer…'
                      : 'Upload a resume and start the interview to answer here…')
                    : 'Ask Mitra about candidates, jobs or documents…'}
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  onKeyDown={handleChatKeyDown}
                />
              </div>
              <button
                type="button"
                className={`as-mic ${isListening ? 'listening' : ''}`}
                onClick={handleMicClick}
                disabled={!activeSessionId || asking || messagesLoading}
                aria-label="Voice input"
                title="Voice input"
              >
                <NwIcon name="mic" />
              </button>
              {asking ? (
                <button
                  type="button"
                  className="as-stop"
                  onClick={handleStop}
                  aria-label="Stop generating"
                  title="Stop generating"
                >
                  <NwIcon name="square" />
                </button>
              ) : (
                <button
                  type="submit"
                  className="as-send"
                  aria-label="Send"
                  disabled={
                    !question.trim()
                    || (!activeSessionId && !interviewModeActive)
                    || interviewSubmitting
                    || (interviewModeActive && interviewSession?.status !== 'in_progress')
                    || (interviewModeActive && !interviewQuestion)
                  }
                >
                  <NwIcon name="arrow-up" />
                </button>
              )}
            </div>
            <small className="muted">{isListening ? 'Listening… tap the microphone to stop.' : 'Enter for a new line · Ctrl+Enter to send. Mitra can make mistakes.'}</small>
          </form>
        </section>

        <aside className={`as-rail`} aria-label="Your AI Team">
          <section className="card card-pad as-team">
            <div className="eyebrow">Your AI team</div>
            <ul className="as-agents">
              {AGENTS.map((agent) => (
                <li key={agent.name}>
                  <NwIcon name={agent.icon} />
                  <span>{agent.name}</span>
                  {agent.active ? (
                    <span className="chip chip-green">Active</span>
                  ) : (
                    <span className="chip chip-gray" title="Available in Mitra Assistant">Mitra</span>
                  )}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>

      {chatLimitOpen && (
        <div className="as-modal-overlay" onClick={() => setChatLimitOpen(false)}>
          <div
            className="as-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="chat-limit-title"
            onClick={(event) => event.stopPropagation()}
          >
            <span className="as-modal-icon"><NwIcon name="warning" /></span>
            <h3 className="as-modal-title" id="chat-limit-title">Chat Limit Exceeded</h3>
            <p className="as-modal-message">
              You have reached the maximum limit of {MAX_CHAT_SESSIONS_PER_USER} chat conversations for your account. You cannot create a new conversation right now.
            </p>
            <p className="as-modal-counter">{MAX_CHAT_SESSIONS_PER_USER} / {MAX_CHAT_SESSIONS_PER_USER} Chats Used</p>
            <button type="button" className="btn btn-primary as-modal-close" onClick={() => setChatLimitOpen(false)}>
              Got it
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
