import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Loading from '../components/Loading'
import { getCurrentUser, isSupabaseConfigured, signOut } from '../services/auth'
import { listCandidates } from '../services/candidates'
import { checkHealth } from '../services/health'
import { listJobs } from '../services/jobs'
import {
  analyzeJob,
  deleteDocument,
  draftCommunication,
  listDocuments,
  matchCandidate,
  scheduleSuggestions,
  uploadDocument,
} from '../services/rag'
import {
  createChatSession,
  deleteAllChatSessions,
  deleteChatSession,
  listChatMessages,
  listChatSessions,
  renameChatSession,
  sendChatMessage,
} from '../services/chat'
import { moveSessionToTop, sessionTimeLabel, toChatMessage } from '../utils/chat'
import {
  buildConversationPrintHtml,
  buildHistoryPrintHtml,
  conversationExportFilename,
  historyExportFilename,
  openPrintDocument,
} from '../utils/chatExport'

const TABS = [
  { id: 'documents', label: 'Documents' },
  { id: 'analysis', label: 'Job analysis' },
  { id: 'matching', label: 'Matching' },
  { id: 'chatbot', label: 'Chatbot' },
  { id: 'emails', label: 'Emails' },
  { id: 'scheduling', label: 'Scheduling' },
]

const SOURCE_TYPES = ['resume', 'job_description', 'knowledge']
const DRAFT_TYPES = [
  { id: 'interview_invitation', label: 'Interview invitation' },
  { id: 'follow_up', label: 'Follow up' },
  { id: 'application_status', label: 'Application status' },
]

const GREETING_PATTERN =
  /^(hi+|hello+|hey+(?:\s+there)?|good\s+(?:morning|afternoon|evening)|thanks(?:\s+you)?|thank\s+you|how\s+are\s+you(?:\s+doing)?|what'?s\s+up|howdy|greetings|yo)\b[\s!.?,]*$/i

const GREETING_REPLY =
  "Hello! I'm your recruiter AI assistant. I can answer questions about your uploaded documents, candidates, and jobs — for example: summarize a candidate, find who has specific skills, or explain a job's requirements. Ask me a recruitment question to get started."

const SUGGESTED_QUESTIONS = [
  'Summarize my candidates.',
  'Find candidates matching a job.',
  'Which candidates have Python experience?',
  'Explain the requirements of my latest job.',
  "Identify missing skills in a candidate's profile.",
]

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

function SkillChips({ items }) {
  if (!items || items.length === 0) return <p className="field-hint">None listed.</p>
  return (
    <ul className="chip-list">
      {items.map((item) => (
        <li key={item} className="chip">
          {item}
        </li>
      ))}
    </ul>
  )
}

function EvidenceList({ items }) {
  if (!items || items.length === 0) return <p className="field-hint">No evidence references.</p>
  return (
    <ul className="recent-list">
      {items.map((item, index) => (
        <li key={index}>
          <span>
            {item && typeof item === 'object'
              ? `${item.source_type || ''}${
                  item.source_type ? ' · ' : ''
                }${item.filename || item.source || ''}${
                  item.chunk_index !== undefined
                    ? ` · chunk ${item.chunk_index}`
                    : ''
                }${
                  item.score !== undefined
                    ? ` · score ${Number(item.score).toFixed(3)}`
                    : ''
                }`
              : String(item)}
          </span>
        </li>
      ))}
    </ul>
  )
}

function PencilIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M4 20h4l10-10-4-4L4 16v4Z" strokeLinejoin="round" />
      <path d="m13 6 4 4" strokeLinecap="round" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="14"
      height="14"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path
        d="M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

function MicrophoneIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z" />
      <path d="M11 11l-1 5h2l-1-5z" />
      <path d="M12 20v2" />
    </svg>
  )
}

function StopMicrophoneIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="18"
      height="18"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="12" height="12" />
    </svg>
  )
}

function SpeakerIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <path d="M3 10v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2z" />
      <path d="M8 2v4M16 2v4M9 8h6" />
    </svg>
  )
}

function StopSpeakerIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      width="16"
      height="16"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      aria-hidden="true"
    >
      <rect x="6" y="6" width="12" height="12" />
    </svg>
  )
}

export default function AIAssistant() {
  const navigate = useNavigate()
  const [tab, setTab] = useState('documents')
  const [jobs, setJobs] = useState([])
  const [candidates, setCandidates] = useState([])
  const [documents, setDocuments] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let active = true

    async function loadWorkspace() {
      setLoading(true)
      setError('')
      try {
        const [documentData, jobData, candidateData] = await Promise.all([
          listDocuments(),
          listJobs(),
          listCandidates(),
        ])
        if (!active) return
        setDocuments(documentData.documents || [])
        setJobs(jobData)
        setCandidates(candidateData)
      } catch (err) {
        if (active) setError(err.message)
      } finally {
        if (active) setLoading(false)
      }

      try {
        await checkHealth()
        if (active) setAssistantOnline(true)
      } catch {
        if (active) setAssistantOnline(false)
      }
    }

    loadWorkspace()
    return () => {
      active = false
    }
  }, [reloadKey])

  const [uploadFile, setUploadFile] = useState(null)
  const [uploadSourceType, setUploadSourceType] = useState('resume')
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [deletingId, setDeletingId] = useState(null)

  const [analysisJobId, setAnalysisJobId] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [analysisError, setAnalysisError] = useState('')
  const [analysis, setAnalysis] = useState(null)

  const [matchCandidateId, setMatchCandidateId] = useState('')
  const [matchJobId, setMatchJobId] = useState('')
  const [matching, setMatching] = useState(false)
  const [matchError, setMatchError] = useState('')
  const [match, setMatch] = useState(null)

  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [chatError, setChatError] = useState('')
  const [messages, setMessages] = useState([])
  const [lastQuestion, setLastQuestion] = useState('')
  const [assistantOnline, setAssistantOnline] = useState(null)
  const threadRef = useRef(null)

  const [sessions, setSessions] = useState([])
  const [sessionsLoading, setSessionsLoading] = useState(true)
  const [sessionsError, setSessionsError] = useState('')
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [creatingSession, setCreatingSession] = useState(false)
  const [deletingSessionId, setDeletingSessionId] = useState(null)
  const [renamingId, setRenamingId] = useState(null)
  const [renameTitle, setRenameTitle] = useState('')
  const [renaming, setRenaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [chatNotice, setChatNotice] = useState('')
  const [showGuide, setShowGuide] = useState(false)
  const [accountEmail, setAccountEmail] = useState('')
  const [signingOut, setSigningOut] = useState(false)
  const [signOutError, setSignOutError] = useState('')
  const [exportingHistory, setExportingHistory] = useState(false)
  const [exportProgress, setExportProgress] = useState(null)
  const [confirmClearAll, setConfirmClearAll] = useState(false)
  const [clearingHistory, setClearingHistory] = useState(false)
  const [historyNotice, setHistoryNotice] = useState('')
  const [historyError, setHistoryError] = useState('')

  const messageRequestId = useRef(0)
  const creatingSessionRef = useRef(false)
  const activeSessionRef = useRef(null)

  const [isListening, setIsListening] = useState(false)
  const [recognition, setRecognition] = useState(null)
  const [voiceReplyError, setVoiceReplyError] = useState('')

  const [isSpeaking, setIsSpeaking] = useState(false)
  const [speakingMessageId, setSpeakingMessageId] = useState(null)
  const speechUtteranceRef = useRef(null)

  const [draftType, setDraftType] = useState('interview_invitation')
  const [draftCandidateId, setDraftCandidateId] = useState('')
  const [draftJobId, setDraftJobId] = useState('')
  const [draftNotes, setDraftNotes] = useState('')
  const [drafting, setDrafting] = useState(false)
  const [draftError, setDraftError] = useState('')
  const [draft, setDraft] = useState(null)

  const [scheduleJobId, setScheduleJobId] = useState('')
  const [scheduleCandidateId, setScheduleCandidateId] = useState('')
  const [scheduleDateStart, setScheduleDateStart] = useState('')
  const [scheduleDateEnd, setScheduleDateEnd] = useState('')
  const [busySlotsText, setBusySlotsText] = useState('')
  const [scheduling, setScheduling] = useState(false)
  const [scheduleError, setScheduleError] = useState('')
  const [schedule, setSchedule] = useState(null)

  async function handleUpload(event) {
    event.preventDefault()
    setUploadError('')

    if (!uploadFile) {
      setUploadError('Choose a file to upload.')
      return
    }

    setUploading(true)
    try {
      await uploadDocument(uploadFile, uploadSourceType)
      setUploadFile(null)
      setReloadKey((key) => key + 1)
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setUploading(false)
    }
  }

  async function handleDeleteDocument(document) {
    const confirmed = window.confirm(
      `Delete "${document.filename}"? This action cannot be undone.`,
    )
    if (!confirmed) return

    setDeletingId(document.document_id)
    setUploadError('')
    try {
      await deleteDocument(document.document_id)
      setReloadKey((key) => key + 1)
    } catch (err) {
      setUploadError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  async function handleAnalyze(event) {
    event.preventDefault()
    setAnalysisError('')

    if (!analysisJobId) {
      setAnalysisError('Select a job to analyze.')
      return
    }

    setAnalyzing(true)
    try {
      const result = await analyzeJob(analysisJobId)
      setAnalysis(result.analysis)
    } catch (err) {
      setAnalysisError(err.message)
    } finally {
      setAnalyzing(false)
    }
  }

  async function handleMatch(event) {
    event.preventDefault()
    setMatchError('')

    if (!matchCandidateId || !matchJobId) {
      setMatchError('Select both a candidate and a job.')
      return
    }

    setMatching(true)
    try {
      const result = await matchCandidate(matchCandidateId, matchJobId)
      setMatch(result.match)
    } catch (err) {
      setMatchError(err.message)
    } finally {
      setMatching(false)
    }
  }

  async function openSession(sessionId) {
    if (!sessionId) return

    const requestId = messageRequestId.current + 1
    messageRequestId.current = requestId
    activeSessionRef.current = sessionId
    setActiveSessionId(sessionId)
    setMessages([])
    setMessagesLoading(true)
    setChatError('')
    setChatNotice('')
    setLastQuestion('')
    setSidebarOpen(false)
    stopSpeaking()

    try {
      const data = await listChatMessages(sessionId)
      if (messageRequestId.current !== requestId) return
      setMessages((Array.isArray(data) ? data : []).map(toChatMessage))
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
      setSessions((current) => [
        session,
        ...current.filter((item) => item.id !== session.id),
      ])
      setActiveSessionId(session.id)
      setMessages([])
      setMessagesLoading(false)
      setChatNotice('')
      setLastQuestion('')
      setSidebarOpen(false)
      stopSpeaking()
    } catch (err) {
      setSessionsError(err.message)
    } finally {
      creatingSessionRef.current = false
      setCreatingSession(false)
    }
  }

  async function reloadSessions() {
    setSessionsLoading(true)
    setSessionsError('')

    try {
      const data = await listChatSessions()
      const list = Array.isArray(data) ? data : []
      setSessions(list)
      if (list.length > 0) {
        await openSession(list[0].id)
      } else {
        activeSessionRef.current = null
        setActiveSessionId(null)
        setMessages([])
      }
    } catch (err) {
      setSessionsError(err.message)
    } finally {
      setSessionsLoading(false)
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
      setSessions((current) =>
        current.filter((item) => item.id !== session.id),
      )

      if (activeSessionRef.current === session.id) {
        messageRequestId.current += 1
        activeSessionRef.current = null
        setActiveSessionId(null)
        setMessages([])
        setMessagesLoading(false)
        setChatError('')
        setChatNotice('')
        setLastQuestion('')
        setSidebarOpen(false)

        const nextSession = sessions.find((item) => item.id !== session.id)
        if (nextSession) await openSession(nextSession.id)
      }

      if (renamingId === session.id) cancelRename()
    } catch (err) {
      setSessionsError(err.message)
    } finally {
      setDeletingSessionId(null)
    }
  }

  function handleExportConversation() {
    if (!activeSessionId || messagesLoading) return

    const session = sessions.find((item) => item.id === activeSessionId)
    const title = session?.title || 'Conversation'
    const generatedAt = new Date()
    const filename = conversationExportFilename(title, generatedAt)
    const html = buildConversationPrintHtml({
      title,
      messages: messages.filter((message) => !message.failed),
      generatedAt,
    })

    if (!openPrintDocument(html, filename)) {
      setChatNotice('')
      setChatError(
        'The print window was blocked. Allow pop-ups for this site, then try again.',
      )
      return
    }

    setChatError('')
    setChatNotice(
      'Printable conversation opened. Choose “Save as PDF” in the print dialog.',
    )
  }

  async function handleExportHistory() {
    if (exportingHistory) return

    if (sessions.length === 0) {
      setHistoryError('')
      setHistoryNotice('There are no conversations to export.')
      return
    }

    setExportingHistory(true)
    setHistoryError('')
    setHistoryNotice('')
    setExportProgress({ done: 0, total: sessions.length })

    try {
      const conversations = []
      let skipped = 0

      for (let index = 0; index < sessions.length; index += 1) {
        const session = sessions[index]
        try {
          const data = await listChatMessages(session.id)
          conversations.push({
            title: session.title || 'Conversation',
            messages: (Array.isArray(data) ? data : []).map(toChatMessage),
          })
        } catch {
          skipped += 1
        }
        setExportProgress({ done: index + 1, total: sessions.length })
      }

      if (conversations.length === 0) {
        throw new Error(
          'None of the conversations could be exported. Please try again.',
        )
      }

      const generatedAt = new Date()
      const html = buildHistoryPrintHtml({ conversations, generatedAt })

      if (!openPrintDocument(html, historyExportFilename(generatedAt))) {
        throw new Error(
          'The print window was blocked. Allow pop-ups for this site, then try again.',
        )
      }

      setHistoryNotice(
        skipped > 0
          ? `Opened ${conversations.length} conversations for printing. ${skipped} could not be loaded.`
          : `Opened ${conversations.length} conversations for printing. Choose “Save as PDF” in the print dialog.`,
      )
    } catch (err) {
      setHistoryError(err.message)
    } finally {
      setExportingHistory(false)
      setExportProgress(null)
    }
  }

  async function handleClearHistory() {
    if (clearingHistory) return

    setClearingHistory(true)
    setHistoryError('')
    setHistoryNotice('')

    try {
      const result = await deleteAllChatSessions()
      const deleted =
        result && typeof result.deleted === 'number'
          ? result.deleted
          : sessions.length

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
      setSidebarOpen(false)
      setConfirmClearAll(false)
      cancelRename()

      setHistoryNotice(
        deleted > 0
          ? `Deleted ${deleted} conversation${
              deleted === 1 ? '' : 's'
            } and all of their messages.`
          : 'There was no chat history to delete.',
      )
    } catch (err) {
      setHistoryError(err.message)
    } finally {
      setClearingHistory(false)
    }
  }

  async function sendQuestion(rawQuestion) {
    const trimmed = rawQuestion.trim()
    if (!trimmed || asking || messagesLoading || creatingSession || !activeSessionId) return

    const sessionId = activeSessionId
    const requestId = messageRequestId.current
    const optimisticId = `local-${Date.now()}-${Math.random()}`

    setChatError('')
    setChatNotice('')
    setQuestion('')
    setLastQuestion(trimmed)
    setMessages((current) => [
      ...current.filter((message) => !message.failed),
      { id: optimisticId, role: 'user', text: trimmed, time: nowLabel() },
    ])
    setAsking(true)

    if (GREETING_PATTERN.test(trimmed)) {
      setMessages((current) => [
        ...current,
        {
          id: `${optimisticId}-reply`,
          role: 'assistant',
          text: GREETING_REPLY,
          hasEvidence: true,
          time: nowLabel(),
        },
      ])
      setAsking(false)
      return
    }

    try {
      const exchange = await sendChatMessage(sessionId, trimmed)
      if (
        messageRequestId.current !== requestId ||
        activeSessionRef.current !== sessionId
      ) {
        return
      }

      setMessages((current) => [
        ...current.filter((message) => message.id !== optimisticId),
        toChatMessage(exchange.user_message),
        toChatMessage(exchange.assistant_message),
      ])
      setSessions((current) => moveSessionToTop(current, sessionId))
    } catch (err) {
      if (
        messageRequestId.current !== requestId ||
        activeSessionRef.current !== sessionId
      ) {
        return
      }

      setMessages((current) =>
        current.map((message) =>
          message.id === optimisticId ? { ...message, failed: true } : message,
        ),
      )
      setChatError(err.message)
    } finally {
      setAsking(false)
    }
  }

  async function handleAsk(event) {
    event.preventDefault()
    await sendQuestion(question)
  }

  function handleChatKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      handleAsk(event)
    }
  }

  function handleRetry() {
    if (!lastQuestion || asking || messagesLoading) return
    setMessages((current) => current.filter((message) => !message.failed))
    sendQuestion(lastQuestion)
  }

  function handleClearChat() {
    const activeSession = sessions.find((item) => item.id === activeSessionId)
    if (activeSession) handleDeleteSession(activeSession)
  }

  async function handleLogout() {
    if (signingOut) return
    setSigningOut(true)
    setSignOutError('')
    try {
      await signOut()
      navigate('/login', { replace: true })
    } catch (err) {
      setSignOutError(err.message)
    } finally {
      setSigningOut(false)
    }
  }

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
          const localOnly = current.filter(
            (session) => !fetched.has(session.id),
          )
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
    let active = true
    if (isSupabaseConfigured) {
      getCurrentUser()
        .then((user) => {
          if (active && user) setAccountEmail(user.email || '')
        })
        .catch(() => {})
    }
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    if (!window.SpeechRecognition && !window.webkitSpeechRecognition) {
      return;
    }

    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const instance = new SR();
    instance.lang = 'en-US';
    instance.interimResults = false;
    instance.maxAlternatives = 1;

    instance.onstart = () => setIsListening(true);
    instance.onend = () => setIsListening(false);
    instance.onerror = (event) => {
      if (event.error === 'not-allowed') {
        setVoiceReplyError('Microphone access denied. Please allow microphone permission.');
      } else {
        setVoiceReplyError('');
      }
    };
    instance.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      const normalized = transcript.replace(/^\s+|\s+$/g, '');
      setQuestion(normalized);
    };

    setRecognition(instance);

    return () => {
      instance.stop();
    };
  }, []);

  useEffect(() => {
    return () => {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);
  const toggleListening = () => {
    if (!recognition) return;
    if (isListening) {
      recognition.stop();
      setIsListening(false);
    } else {
      recognition.start();
      setIsListening(true);
    }
  };

  const speakMessage = (messageId, text) => {
    if (!window.speechSynthesis || !text?.trim()) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    utterance.rate = 1;
    utterance.pitch = 1;
    utterance.onstart = () => {
      setIsSpeaking(true);
      setSpeakingMessageId(messageId);
    };
    utterance.onend = () => {
      setIsSpeaking(false);
      setSpeakingMessageId(null);
    };
    utterance.onerror = (event) => {
      setIsSpeaking(false);
      setSpeakingMessageId(null);
      if (event.error) {
        setVoiceReplyError(`Speech playback error: ${event.error}`);
      }
    };
    window.speechSynthesis.speak(utterance);
    speechUtteranceRef.current = utterance;
  };

  const stopSpeaking = () => {
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    setIsSpeaking(false);
    setSpeakingMessageId(null);
  };

  const handleMicClick = () => {
    if (!activeSessionId || asking || messagesLoading) return;
    toggleListening();
  };

  const handleSpeakClick = (messageId, text) => {
    if (isSpeaking && speakingMessageId === messageId) {
      stopSpeaking();
    } else {
      speakMessage(messageId, text);
    }
  };

  async function handleDraft(event) {
    event.preventDefault()
    setDraftError('')
    setDrafting(true)
    try {
      const result = await draftCommunication({
        draft_type: draftType,
        job_id: draftJobId || null,
        candidate_id: draftCandidateId || null,
        custom_notes: draftNotes.trim() || null,
      })
      setDraft(result.draft)
    } catch (err) {
      setDraftError(err.message)
    } finally {
      setDrafting(false)
    }
  }

  async function handleSchedule(event) {
    event.preventDefault()
    setScheduleError('')

    if (!scheduleDateStart || !scheduleDateEnd) {
      setScheduleError('Choose both a start and an end date.')
      return
    }

    const busySlots = busySlotsText
      .split('\n')
      .map((slot) => slot.trim())
      .filter(Boolean)

    setScheduling(true)
    try {
      const result = await scheduleSuggestions({
        job_id: scheduleJobId || null,
        candidate_id: scheduleCandidateId || null,
        date_start: scheduleDateStart,
        date_end: scheduleDateEnd,
        busy_slots: busySlots,
      })
      setSchedule(result.plan)
    } catch (err) {
      setScheduleError(err.message)
    } finally {
      setScheduling(false)
    }
  }

  if (loading) {
    return (
      <div className="page ai-page-dark">
        <Loading label="Loading AI Assistant..." />
      </div>
    )
  }

  return (
    <div className="page ai-page-dark">
      <header className="ai-topbar">
        <div className="ai-topbar-brand">
          <span className="ai-topbar-mark" aria-hidden="true">
            AR
          </span>
          AI Recruitment Agent
        </div>
        <nav className="ai-topbar-tabs" aria-label="AI Assistant sections">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`ai-tab ${tab === item.id ? 'ai-tab-active' : ''}`}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <div className="ai-topbar-user">
          <span className="ai-topbar-email" title={accountEmail || 'Signed in'}>
            {accountEmail || 'Signed in'}
          </span>
          <button
            type="button"
            className="ai-topbar-logout"
            onClick={handleLogout}
            disabled={signingOut}
          >
            {signingOut ? 'Signing out…' : 'Log out'}
          </button>
        </div>
        {signOutError && (
          <p className="ai-topbar-error" role="alert">
            {signOutError}
          </p>
        )}
      </header>

      {error && (
        <div className="alert alert-error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => setReloadKey((key) => key + 1)}
          >
            Retry
          </button>
        </div>
      )}

      {tab === 'documents' && (
        <section className="panel">
          <div className="panel-header">
            <h2>Documents</h2>
            <span className="toolbar-count">
              {documents.length} document{documents.length === 1 ? '' : 's'}
            </span>
          </div>

          <form className="form-grid" onSubmit={handleUpload}>
            <div className="field">
              <label htmlFor="upload-file">File</label>
              <input
                id="upload-file"
                type="file"
                onChange={(event) => setUploadFile(event.target.files[0] || null)}
              />
            </div>

            <div className="field">
              <label htmlFor="upload-source-type">Source type</label>
              <select
                id="upload-source-type"
                value={uploadSourceType}
                onChange={(event) => setUploadSourceType(event.target.value)}
              >
                {SOURCE_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>

            <div className="field field-full">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={uploading}
              >
                {uploading ? 'Uploading...' : 'Upload document'}
              </button>
            </div>
          </form>

          {uploadError && (
            <div className="alert alert-error" role="alert">
              {uploadError}
            </div>
          )}

          {documents.length === 0 ? (
            <div className="empty-state compact">
              <p>No documents uploaded yet.</p>
            </div>
          ) : (
            <ul className="recent-list">
              {documents.map((document) => (
                <li key={document.document_id}>
                  <div>
                    <span>{document.filename}</span>
                    <p>
                      {document.source_type} · {document.chunk_count ?? 0} chunks
                      ·{' '}
                      {document.created_at
                        ? new Date(document.created_at).toLocaleDateString()
                        : 'Unknown date'}
                    </p>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={deletingId === document.document_id}
                    onClick={() => handleDeleteDocument(document)}
                  >
                    {deletingId === document.document_id ? 'Deleting...' : 'Delete'}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === 'analysis' && (
        <section className="panel">
          <div className="panel-header">
            <h2>Job analysis</h2>
          </div>

          <form className="form-grid" onSubmit={handleAnalyze}>
            <div className="field">
              <label htmlFor="analysis-job">Job</label>
              <select
                id="analysis-job"
                value={analysisJobId}
                onChange={(event) => setAnalysisJobId(event.target.value)}
              >
                <option value="">Select a job</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="field field-full">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={analyzing}
              >
                {analyzing ? 'Analyzing...' : 'Analyze job'}
              </button>
            </div>
          </form>

          {analysisError && (
            <div className="alert alert-error" role="alert">
              {analysisError}
            </div>
          )}

          {analysis && (
            <div className="detail-grid">
              <div>
                <dt>Required skills</dt>
                <dd>
                  <SkillChips items={analysis.required_skills} />
                </dd>
              </div>
              <div>
                <dt>Preferred skills</dt>
                <dd>
                  <SkillChips items={analysis.preferred_skills} />
                </dd>
              </div>
              <div>
                <dt>Experience</dt>
                <dd>{analysis.experience ?? 'Not specified'}</dd>
              </div>
              <div>
                <dt>Education</dt>
                <dd>{analysis.education ?? 'Not specified'}</dd>
              </div>
              <div className="field-full">
                <dt>Summary</dt>
                <dd>{analysis.summary ?? 'Not specified'}</dd>
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'matching' && (
        <section className="panel">
          <div className="panel-header">
            <h2>Matching</h2>
          </div>

          <form className="form-grid" onSubmit={handleMatch}>
            <div className="field">
              <label htmlFor="match-candidate">Candidate</label>
              <select
                id="match-candidate"
                value={matchCandidateId}
                onChange={(event) => setMatchCandidateId(event.target.value)}
              >
                <option value="">Select a candidate</option>
                {candidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.full_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="match-job">Job</label>
              <select
                id="match-job"
                value={matchJobId}
                onChange={(event) => setMatchJobId(event.target.value)}
              >
                <option value="">Select a job</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="field field-full">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={matching}
              >
                {matching ? 'Matching...' : 'Match candidate'}
              </button>
            </div>
          </form>

          {matchError && (
            <div className="alert alert-error" role="alert">
              {matchError}
            </div>
          )}

          {match && (
            <div className="detail-grid">
              <div>
                <dt>Matched skills</dt>
                <dd>
                  <SkillChips items={match.matched_skills} />
                </dd>
              </div>
              <div>
                <dt>Missing skills</dt>
                <dd>
                  <SkillChips items={match.missing_skills} />
                </dd>
              </div>
              <div>
                <dt>Relevance score</dt>
                <dd>{match.relevance_score ?? 'Not available'}</dd>
              </div>
              <div className="field-full">
                <dt>Explanation</dt>
                <dd>{match.explanation ?? 'Not available'}</dd>
              </div>
              <div className="field-full">
                <dt>Evidence</dt>
                <dd>
                  <EvidenceList items={match.evidence} />
                </dd>
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'chatbot' && (
        <section className="assistant-layout">
          <aside
            id="chat-session-panel"
            className={`chat-sidebar ${sidebarOpen ? 'chat-sidebar-open' : ''}`}
            aria-label="Chat conversations"
            style={{ width: '22%', flexShrink: 0, borderRight: '1px solid var(--line)' }}
          >
            <div className="chat-sidebar-head">
              <button
                type="button"
                className="btn btn-primary btn-sm chat-new-chat"
                onClick={handleNewChat}
                disabled={creatingSession || asking}
              >
                {creatingSession ? 'Creating…' : '+ New chat'}
              </button>
              <button
                type="button"
                className="chat-sidebar-close"
                onClick={() => setSidebarOpen(false)}
                aria-label="Close conversation list"
                title="Close"
              >
                ×
              </button>
            </div>

            {sessionsError && (
              <div className="chat-sidebar-error">
                <p role="alert">{sessionsError}</p>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={reloadSessions}
                >
                  Retry
                </button>
              </div>
            )}

            {sessionsLoading ? (
              <p className="chat-sidebar-hint" role="status">
                Loading conversations…
              </p>
            ) : sessions.length === 0 ? (
              sessionsError ? null : (
                <div className="chat-sidebar-empty">
                  <p>No conversations yet.</p>
                  <p>Start a new chat to save your history.</p>
                </div>
              )
            ) : (
              <ul className="chat-session-list">
                {sessions.map((session) => {
                  const isActive = session.id === activeSessionId
                  const isRenaming = renamingId === session.id

                  return (
                    <li
                      key={session.id}
                      className={`chat-session ${isActive ? 'chat-session-active' : ''}`}
                    >
                      {isRenaming ? (
                        <form
                          className="chat-rename-form"
                          onSubmit={(event) => handleRename(event, session)}
                        >
                          <input
                            type="text"
                            value={renameTitle}
                            onChange={(event) => setRenameTitle(event.target.value)}
                            onKeyDown={(event) => {
                              if (event.key === 'Escape') cancelRename()
                            }}
                            maxLength={200}
                            aria-label="Conversation title"
                            autoFocus
                          />
                          <button
                            type="submit"
                            className="btn btn-primary btn-sm"
                            disabled={renaming || !renameTitle.trim()}
                          >
                            Save
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={cancelRename}
                            disabled={renaming}
                          >
                            Cancel
                          </button>
                        </form>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="chat-session-select"
                            onClick={() => openSession(session.id)}
                            aria-current={isActive ? 'true' : undefined}
                            disabled={asking}
                          >
                            <span className="chat-session-title">
                              {session.title || 'New conversation'}
                            </span>
                            <span className="chat-session-time">
                              {sessionTimeLabel(session.updated_at)}
                            </span>
                          </button>
                          <div className="chat-session-actions">
                            <button
                              type="button"
                              className="chat-session-action"
                              onClick={() => startRename(session)}
                              aria-label={`Rename ${session.title || 'conversation'}`}
                              title="Rename"
                              disabled={
                                asking ||
                                renaming ||
                                deletingSessionId === session.id
                              }
                            >
                              <PencilIcon />
                            </button>
                            <button
                              type="button"
                              className="chat-session-action chat-session-action-danger"
                              onClick={() => handleDeleteSession(session)}
                              aria-label={`Delete ${session.title || 'conversation'}`}
                              title="Delete"
                              disabled={
                                asking || deletingSessionId === session.id
                              }
                            >
                              {deletingSessionId === session.id ? (
                                '…'
                              ) : (
                                <TrashIcon />
                              )}
                            </button>
                          </div>
                        </>
                      )}
                    </li>
                  )
                })}
              </ul>
            )}

            <div className="chat-history-tools">
              <button
                type="button"
                className="btn btn-secondary btn-sm btn-block"
                onClick={handleExportHistory}
                disabled={
                  exportingHistory ||
                  sessionsLoading ||
                  clearingHistory ||
                  sessions.length === 0
                }
              >
                {exportingHistory
                  ? exportProgress
                    ? `Exporting ${exportProgress.done}/${exportProgress.total}…`
                    : 'Exporting…'
                  : 'Export all (PDF)'}
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm btn-block"
                onClick={() => {
                  setConfirmClearAll(true)
                  setHistoryError('')
                  setHistoryNotice('')
                }}
                disabled={clearingHistory || sessions.length === 0}
              >
                Clear all history
              </button>
            </div>

            {confirmClearAll && sessions.length > 0 && (
              <div
                className="chat-clear-confirm"
                role="alertdialog"
                aria-label="Confirm clearing all chat history"
              >
                <p>
                  <strong>Delete all conversations?</strong>
                </p>
                <p>
                  All {sessions.length} conversation
                  {sessions.length === 1 ? '' : 's'} and every message will be
                  permanently deleted. This cannot be undone.
                </p>
                <div className="chat-clear-confirm-actions">
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={handleClearHistory}
                    disabled={clearingHistory}
                  >
                    {clearingHistory ? 'Deleting…' : 'Delete everything'}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setConfirmClearAll(false)}
                    disabled={clearingHistory}
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {historyNotice && (
              <p className="chat-history-note" role="status">
                {historyNotice}
              </p>
            )}
            {historyError && (
              <p className="chat-history-error" role="alert">
                {historyError}
              </p>
            )}
          </aside>

          {/* Center panel: Conversation */}
          <section className="chat-main" style={{ flex: '1', minWidth: 0, padding: '0 20px' }}>

          {/* Chat message area */}
          <div className="chat">
            <div className="chat-header">
              <div className="chat-identity" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8">
                  <rect x="4" y="7" width="16" height="12" rx="3" />
                  <path d="M12 3v4M9 13h.01M15 13h.01M9.5 16.5c.8.7 2 .7 2.5.5.5.2 1.7.2 2.5-.5" strokeLinecap="round" />
                </svg>
              </div>
              <div>
                <h2>AI Recruitment Assistant</h2>
                <p>
                  Ask questions about your uploaded documents, candidates, and
                  jobs. Answers come from your own files, with sources attached.
                </p>
              </div>
              <span
                className={`chat-status ${
                  assistantOnline === false
                    ? 'chat-status-offline'
                    : assistantOnline === null
                      ? 'chat-status-checking'
                      : ''
                }`}
                role="status"
              >
                <span className="chat-status-dot" aria-hidden="true" />
                {assistantOnline === false
                  ? 'Assistant service unavailable'
                  : assistantOnline === null
                    ? 'Checking connection…'
                    : 'Connected to your workspace'}
              </span>
              <div className="chat-header-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setShowGuide((open) => !open)}
                  aria-expanded={showGuide}
                  title="Show what the assistant can do"
                >
                  What can I do?
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleClearChat}
                  disabled={
                    !activeSessionId ||
                    asking ||
                    deletingSessionId === activeSessionId
                  }
                  title="Delete the current conversation"
                >
                  Clear chat
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={handleExportConversation}
                  disabled={!activeSessionId || messagesLoading || asking}
                  title="Export this conversation as a PDF"
                >
                  Export PDF
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm chat-sidebar-toggle"
                  onClick={() => setSidebarOpen((open) => !open)}
                  aria-expanded={sidebarOpen}
                  aria-controls="chat-session-panel"
                >
                  Conversations
                </button>
              </div>
            </div>

            {showGuide && (
              <div className="chat-guide">
                <h3>What can I do?</h3>
                <p>{GREETING_REPLY}</p>
                <div className="chat-suggestions">
                  {SUGGESTED_QUESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      className="chat-suggestion"
                      onClick={() => {
                        setShowGuide(false)
                        sendQuestion(suggestion)
                      }}
                      disabled={asking || messagesLoading}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {sessionsLoading && !activeSessionId ? (
              <div className="chat-loading" role="status">
                Loading conversations…
              </div>
            ) : sessionsError && !activeSessionId ? (
              <div className="chat-empty">
                <h3>Conversations could not be loaded</h3>
                <p>{sessionsError}</p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={reloadSessions}
                >
                  Retry
                </button>
              </div>
            ) : messagesLoading ? (
              <div className="chat-loading" role="status">
                Loading conversation…
              </div>
            ) : !activeSessionId ? (
              <div className="chat-empty">
                <h3>
                  {sessions.length === 0
                    ? 'No conversations yet'
                    : 'Select a conversation'}
                </h3>
                <p>
                  {sessions.length === 0
                    ? 'Start a new chat to ask about your documents, candidates, and jobs. Your conversation history is saved automatically.'
                    : 'Choose a conversation from the list, or start a new chat.'}
                </p>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={handleNewChat}
                  disabled={creatingSession}
                >
                  {creatingSession ? 'Creating…' : 'Start a new chat'}
                </button>
              </div>
            ) : messages.length === 0 && !asking ? (
              <div className="chat-empty">
                <h3>How can I help you with recruitment today?</h3>
                <div className="chat-suggestions">
                  {SUGGESTED_QUESTIONS.map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      className="chat-suggestion"
                      onClick={() => sendQuestion(suggestion)}
                      disabled={asking || messagesLoading}
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="chat-thread" ref={threadRef}>
                {messages.map((message) => (
                  <article
                    key={message.id}
                    className={`chat-row ${message.role === 'user' ? 'chat-row-user' : 'chat-row-assistant'}`}
                  >
                    <div className={`chat-bubble ${message.role === 'user' ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>
                      <div className="chat-meta">
                        <span className="chat-author">
                          {message.role === 'user' ? 'You' : 'Recruiter AI'}
                        </span>
                        <time className="chat-time">{message.time}</time>
                      </div>
                      {message.role === 'assistant' && window.speechSynthesis && (
                        <button
                          type="button"
                          className={`chat-speak-btn ${isSpeaking && speakingMessageId === message.id ? 'chat-speak-btn-speaking' : ''}`}
                          onClick={() => handleSpeakClick(message.id, message.text)}
                          aria-label={
                            isSpeaking && speakingMessageId === message.id
                              ? 'Stop reading'
                              : 'Read response aloud'
                          }
                          title={
                            isSpeaking && speakingMessageId === message.id
                              ? 'Stop reading'
                              : 'Read response aloud'
                          }
                          disabled={!message.text?.trim()}
                        >
                          {isSpeaking && speakingMessageId === message.id ? (
                            <StopSpeakerIcon />
                          ) : (
                            <SpeakerIcon />
                          )}
                        </button>
                      )}
                      {message.text.split('\n\n').map((paragraph, index) => (
                        <p key={index}>{paragraph}</p>
                      ))}
                      {!message.hasEvidence && message.role === 'assistant' && (
                        <p className="chat-note">
                          No supporting evidence was found in your documents for
                          this question.
                        </p>
                      )}
                      {message.hasEvidence && message.sources && message.sources.length > 0 && (
                        <details className="chat-sources">
                          <summary>Sources ({message.sources.length})</summary>
                          <EvidenceList items={message.sources} />
                        </details>
                      )}
                    </div>
                  </article>
                ))}
                {asking && (
                  <article className="chat-row chat-row-assistant" aria-live="polite">
                    <div className="chat-bubble chat-bubble-assistant">
                      <span className="chat-typing" role="status">
                        <span className="chat-typing-label">Recruiter AI is reviewing your documents</span>
                        <span className="chat-dot" />
                        <span className="chat-dot" />
                        <span className="chat-dot" />
                      </span>
                    </div>
                  </article>
                )}
              </div>
            )}

            {chatError && (
              <div className="alert alert-error chat-alert" role="alert">
                <span>{chatError}</span>
                {activeSessionId && !asking && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={
                      lastQuestion
                        ? handleRetry
                        : () => openSession(activeSessionId)
                    }
                  >
                    Retry
                  </button>
                )}
              </div>
            )}

            {voiceReplyError && (
              <div className="alert alert-error chat-alert" role="alert">
                <span>{voiceReplyError}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setVoiceReplyError('')}
                >
                  Dismiss
                </button>
              </div>
            )}

            {chatNotice && (
              <div className="alert alert-success chat-alert" role="status">
                <span>{chatNotice}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setChatNotice('')}
                >
                  Dismiss
                </button>
              </div>
            )}

            <form className="chat-composer" onSubmit={handleAsk}>
              {/* Attachment area */}
              <div className="chat-attachment">
                <button
                  type="button"
                  className="chat-attachment-btn"
                  onClick={handleAttachFile}
                  disabled={creatingSession || asking}
                  aria-label="Attach files"
                  title="Attach files"
                >
                  <Icon name="attach" size={16} />
                  <span>Attach</span>
                </button>
                {attachedFiles && attachedFiles.map((file, idx) => (
                  <span key={idx} className="chat-attached-file">
                    {file.name}
                    <button
                      type="button"
                      className="chat-remove-attachment"
                      onClick={() => removeAttachment(idx)}
                      aria-label="Remove file"
                      title="Remove file"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>

              <textarea
                id="chat-question"
                rows={2}
                placeholder={
                  activeSessionId
                    ? 'Ask anything about your recruitment data…'
                    : 'Start a new chat to ask a question…'
                }
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                onKeyDown={handleChatKeyDown}
                disabled={
                  asking || messagesLoading || creatingSession || !activeSessionId
                }
              />

              <div className="chat-mic-control">
                <button
                  type="button"
                  className={`chat-mic ${isListening ? 'chat-mic-listening' : ''}`}
                  onClick={handleMicClick}
                  disabled={!activeSessionId || asking || messagesLoading || creatingSession}
                  aria-label={isListening ? 'Stop listening' : 'Start voice input'}
                  title={isListening ? 'Stop listening' : 'Start voice input'}
                >
                  {isListening ? <StopMicrophoneIcon /> : <MicrophoneIcon />}
                </button>
              </div>

              <button
                type="submit"
                className="chat-send"
                disabled={
                  asking ||
                  messagesLoading ||
                  creatingSession ||
                  !activeSessionId ||
                  !question.trim()
                }
                aria-label="Send message"
                title="Send message"
              >
                <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M4 12h14M13 6l6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            </form>
          </div>
          </section>

          {/* Right panel: Your AI Team (18%) */}
          <aside className="ai-team-panel" style={{ width: '18%', flexShrink: 0, paddingLeft: '20px' }} aria-label="Your AI Team">
            <div className="ai-team-header">
              <h2>Your AI Team</h2>
              <span className="ai-team-subtitle">Recruiter support agents</span>
            </div>
            {AGENTS && AGENTS.map((agent) => (
              <div key={agent.id} className="ai-agent-card">
                <div className="ai-agent-header">
                  <Icon name={agent.icon} size={20} />
                  <span className="agent-name">{agent.name}</span>
                </div>
                <div className="agent-description">{agent.description}</div>
                <div className="agent-actions">
                  {agent.actions && agent.actions.map((action) => (
                    <button key={action.id} className="agent-action-btn" onClick={() => handleAgentAction(agent.id, action.id)}>
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </aside>
        </section>
      )}

      {tab === 'emails' && (
        <section className="panel">
          <div className="panel-header">
            <h2>Emails</h2>
            <span className="toolbar-count">Drafts are never sent automatically</span>
          </div>

          <form className="form-grid" onSubmit={handleDraft}>
            <div className="field">
              <label htmlFor="draft-type">Draft type</label>
              <select
                id="draft-type"
                value={draftType}
                onChange={(event) => setDraftType(event.target.value)}
              >
                {DRAFT_TYPES.map((type) => (
                  <option key={type.id} value={type.id}>
                    {type.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="draft-candidate">Candidate (optional)</label>
              <select
                id="draft-candidate"
                value={draftCandidateId}
                onChange={(event) => setDraftCandidateId(event.target.value)}
              >
                <option value="">No candidate</option>
                {candidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.full_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="draft-job">Job (optional)</label>
              <select
                id="draft-job"
                value={draftJobId}
                onChange={(event) => setDraftJobId(event.target.value)}
              >
                <option value="">No job</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="field field-full">
              <label htmlFor="draft-notes">Custom notes (optional)</label>
              <textarea
                id="draft-notes"
                rows={4}
                placeholder="Anything the AI should consider when drafting."
                value={draftNotes}
                onChange={(event) => setDraftNotes(event.target.value)}
              />
            </div>

            <div className="field field-full">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={drafting}
              >
                {drafting ? 'Drafting...' : 'Draft communication'}
              </button>
            </div>
          </form>

          {draftError && (
            <div className="alert alert-error" role="alert">
              {draftError}
            </div>
          )}

          {draft && (
            <div className="detail-section">
              <div className="field">
                <label htmlFor="draft-subject">Subject</label>
                <input
                  id="draft-subject"
                  type="text"
                  readOnly
                  value={draft.subject ?? ''}
                />
              </div>
              <div className="field">
                <label htmlFor="draft-body">Body</label>
                <textarea id="draft-body" rows={10} readOnly value={draft.body ?? ''} />
              </div>
            </div>
          )}
        </section>
      )}

      {tab === 'scheduling' && (
        <section className="panel">
          <div className="panel-header">
            <h2>Scheduling</h2>
            <span className="toolbar-count">Suggestions only, nothing is booked</span>
          </div>

          <form className="form-grid" onSubmit={handleSchedule}>
            <div className="field">
              <label htmlFor="schedule-job">Job (optional)</label>
              <select
                id="schedule-job"
                value={scheduleJobId}
                onChange={(event) => setScheduleJobId(event.target.value)}
              >
                <option value="">No job</option>
                {jobs.map((job) => (
                  <option key={job.id} value={job.id}>
                    {job.title}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="schedule-candidate">Candidate (optional)</label>
              <select
                id="schedule-candidate"
                value={scheduleCandidateId}
                onChange={(event) => setScheduleCandidateId(event.target.value)}
              >
                <option value="">No candidate</option>
                {candidates.map((candidate) => (
                  <option key={candidate.id} value={candidate.id}>
                    {candidate.full_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="schedule-start">Date start</label>
              <input
                id="schedule-start"
                type="date"
                value={scheduleDateStart}
                onChange={(event) => setScheduleDateStart(event.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="schedule-end">Date end</label>
              <input
                id="schedule-end"
                type="date"
                value={scheduleDateEnd}
                onChange={(event) => setScheduleDateEnd(event.target.value)}
              />
            </div>

            <div className="field field-full">
              <label htmlFor="schedule-busy">Busy slots</label>
              <textarea
                id="schedule-busy"
                rows={4}
                placeholder={'One per line, e.g.\n2026-11-16 09:00-10:00'}
                value={busySlotsText}
                onChange={(event) => setBusySlotsText(event.target.value)}
              />
              <p className="field-hint">One busy slot per line.</p>
            </div>

            <div className="field field-full">
              <button
                className="btn btn-primary"
                type="submit"
                disabled={scheduling}
              >
                {scheduling ? 'Suggesting...' : 'Suggest slots'}
              </button>
            </div>
          </form>

          {scheduleError && (
            <div className="alert alert-error" role="alert">
              {scheduleError}
            </div>
          )}

          {schedule && (
            <div className="detail-grid">
              <div className="field-full">
                <dt>Suggested slots</dt>
                <dd>
                  <EvidenceList items={schedule.suggestions} />
                </dd>
              </div>
              <div className="field-full">
                <dt>Conflicts</dt>
                <dd>
                  <EvidenceList items={schedule.conflicts} />
                </dd>
              </div>
            </div>
          )}
        </section>
      )}
    </div>
  )
}
