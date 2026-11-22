const PRINT_STYLES = `
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: #ffffff; }
body {
  color: #182132;
  font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Arial, sans-serif;
  font-size: 11.5pt;
  line-height: 1.55;
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}
.document { max-width: 780px; margin: 0 auto; padding: 26px 30px 40px; }
.doc-head { padding-bottom: 14px; margin-bottom: 20px; border-bottom: 2px solid #4f46e5; }
.doc-kicker {
  margin: 0 0 4px;
  color: #4f46e5;
  font-size: 8.5pt;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
h1 { margin: 0; font-size: 20pt; line-height: 1.2; }
h2 { margin: 0; font-size: 15pt; line-height: 1.25; }
.doc-meta { margin: 6px 0 0; color: #667085; font-size: 9.5pt; }
.message {
  padding: 10px 14px;
  margin: 0 0 12px;
  border: 1px solid #e2e7f0;
  border-left: 4px solid #94a3b8;
  border-radius: 6px;
}
.message-user { border-left-color: #4f46e5; background: #f8f9fd; }
.message-assistant { border-left-color: #94a3b8; }
.message-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}
.role {
  color: #344054;
  font-size: 9pt;
  font-weight: 700;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.message-user .role { color: #4338ca; }
.message-head time { color: #667085; font-size: 9pt; white-space: nowrap; }
.message-body p {
  margin: 0 0 8px;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}
.message-body p:last-child { margin-bottom: 0; }
.note { margin: 8px 0 0; color: #b54708; font-size: 9.5pt; font-style: italic; }
.sources { margin-top: 10px; padding-top: 8px; border-top: 1px dashed #d0d5dd; }
.sources h3 {
  margin: 0 0 4px;
  color: #475467;
  font-size: 8.5pt;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}
.sources ol { margin: 0; padding-left: 18px; }
.sources li { color: #475467; font-size: 9.5pt; overflow-wrap: anywhere; }
.attachments { margin-bottom: 8px; }
.attachments strong { display: block; color: #344054; font-size: 9.5pt; }
.attachments span { color: #667085; font-size: 8.5pt; }
.empty { color: #667085; font-style: italic; }
.conversation { break-before: page; }
.conversation:first-of-type { break-before: auto; }
.conversation-head { padding-bottom: 10px; margin-bottom: 16px; border-bottom: 1px solid #e2e7f0; }
.report-category { display: grid; gap: 4px; margin-bottom: 8px; }
.report-category-label { color: #344054; font-size: 9.5pt; font-weight: 700; text-transform: uppercase; }
.report-category-bar { height: 8px; border-radius: 4px; background: #eef1f7; overflow: hidden; }
.report-category-fill { height: 100%; background: #4f46e5; border-radius: 4px; }
.report-category-value { color: #667085; font-size: 9pt; }
.report-section-title { color: #344054; font-size: 11pt; font-weight: 700; margin: 10px 0 6px; }
.doc-foot {
  margin-top: 24px;
  padding-top: 10px;
  border-top: 1px solid #e2e7f0;
  color: #98a2b3;
  font-size: 8.5pt;
}
@media print {
  .document { max-width: none; padding: 0; }
}
`

function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

function toDate(value) {
  if (value instanceof Date) return value
  const date = value ? new Date(value) : new Date()
  return Number.isNaN(date.getTime()) ? new Date() : date
}

export function formatExportTimestamp(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString([], {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function formatGeneratedAt(value) {
  return formatExportTimestamp(toDate(value).toISOString())
}

function dateStamp(value) {
  const date = toDate(value)
  const pad = (number) => String(number).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

function slugify(title) {
  const slug = String(title || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60)
    .replace(/-+$/g, '')
  return slug || 'conversation'
}

export function conversationExportFilename(title, generatedAt) {
  return `conversation-${slugify(title)}-${dateStamp(generatedAt)}.pdf`
}

export function interviewReportFilename(candidateName, generatedAt) {
  const slug = slugify(`Mock Interview Report ${candidateName}`) || 'interview-report'
  return `interview-report-${slug}-${dateStamp(generatedAt)}.pdf`
}

export function historyExportFilename(generatedAt) {
  return `chat-history-${dateStamp(generatedAt)}.pdf`
}

function sourceLabel(item) {
  if (!item || typeof item !== 'object') return String(item ?? '')
  const parts = []
  if (item.source_type) parts.push(item.source_type)
  if (item.filename || item.source) parts.push(item.filename || item.source)
  if (item.chunk_index !== undefined && item.chunk_index !== null) {
    parts.push(`chunk ${item.chunk_index}`)
  }
  const score = Number(item.score)
  if (item.score !== undefined && item.score !== null && Number.isFinite(score)) {
    parts.push(`score ${score.toFixed(3)}`)
  }
  return parts.join(' · ')
}

function messageBody(text) {
  const blocks = String(text ?? '')
    .split(/\n{2,}/)
    .filter((block) => block.trim() !== '')
  if (blocks.length === 0) return '<p class="empty">No content.</p>'
  return blocks.map((block) => `<p>${escapeHtml(block)}</p>`).join('')
}

function messageHtml(message) {
  const isUser = message.role === 'user'
  const sources = Array.isArray(message.sources) ? message.sources : []
  const timestamp =
    formatExportTimestamp(message.createdAt) || message.time || ''

  const evidenceNote =
    !isUser && message.hasEvidence === false
      ? '<p class="note">No supporting evidence was found in the uploaded documents for this question.</p>'
      : ''

  const sourcesHtml =
    sources.length > 0
      ? `<div class="sources"><h3>Sources</h3><ol>${sources
          .map((source) => `<li>${escapeHtml(sourceLabel(source))}</li>`)
          .join('')}</ol></div>`
      : ''

  const attachments = Array.isArray(message.attachments) ? message.attachments : []
  const attachmentsHtml = attachments.length
    ? `<div class="attachments">${attachments
        .map(
          (item) =>
            `<strong>${escapeHtml(item?.name || 'Attachment')}</strong><span>${escapeHtml(
              [item?.sourceType, item?.size ? `${item.size} bytes` : '', item?.chunkCount ? `${item.chunkCount} chunks` : '']
                .filter(Boolean)
                .join(' · '),
            )}</span>`,
        )
        .join('')}</div>`
    : ''

  return `<article class="message ${isUser ? 'message-user' : 'message-assistant'}">
<header class="message-head"><span class="role">${isUser ? 'You' : 'Recruiter AI'}</span><time>${escapeHtml(timestamp)}</time></header>
<div class="message-body">${attachmentsHtml}${messageBody(message.text)}</div>
${evidenceNote}${sourcesHtml}
</article>`
}

function documentShell({ title, heading, meta, generated, body }) {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>${escapeHtml(title)}</title>
<style>${PRINT_STYLES}</style>
</head>
<body>
<main class="document">
<header class="doc-head">
<p class="doc-kicker">AI Recruitment Agent</p>
<h1>${escapeHtml(heading)}</h1>
<p class="doc-meta">${escapeHtml(meta)}</p>
</header>
${body}
<footer class="doc-foot">Generated by AI Recruitment Agent · ${escapeHtml(generated)}</footer>
</main>
</body>
</html>`
}

export function buildConversationPrintHtml({ title, messages, generatedAt } = {}) {
  const list = Array.isArray(messages) ? messages : []
  const safeTitle = (title || 'Conversation').trim() || 'Conversation'
  const generated = formatGeneratedAt(generatedAt)
  const body =
    list.length > 0
      ? list.map((message) => messageHtml(message)).join('\n')
      : '<p class="empty">This conversation has no messages yet.</p>'

  return documentShell({
    title: conversationExportFilename(safeTitle, generatedAt).replace(
      /\.pdf$/i,
      '',
    ),
    heading: safeTitle,
    meta: `Generated ${generated} · ${list.length} message${
      list.length === 1 ? '' : 's'
    }`,
    generated,
    body,
  })
}

export function buildInterviewPrintHtml({
  report,
  candidateName,
  resumeFilename,
  generatedAt,
} = {}) {
  const generated = formatGeneratedAt(generatedAt)
  const score = Number(report?.score ?? 0)
  const level = String(report?.level || 'Needs Improvement')
  const answeredQuestions = Array.isArray(report?.answered_questions)
    ? report.answered_questions
    : []
  const strengths = Array.isArray(report?.strengths) ? report.strengths : []
  const areas = Array.isArray(report?.areas_for_improvement)
    ? report.areas_for_improvement
    : []
  const recommendations = Array.isArray(report?.recommendations)
    ? report.recommendations
    : []
  const categoryScores = report?.category_scores || {}
  const answeredNumbers = Array.isArray(report?.answered_question_numbers)
    ? report.answered_question_numbers
    : []
  const unansweredNumbers = Array.isArray(report?.unanswered_question_numbers)
    ? report.unanswered_question_numbers
    : []

  const categoriesHtml = Object.entries(categoryScores)
    .map(
      ([key, value]) => `
        <div class="report-category">
          <span class="report-category-label">${escapeHtml(
            String(key).replace(/_/g, ' '),
          )}</span>
          <div class="report-category-bar">
            <div class="report-category-fill" style="width: ${((Number(value) || 0) / 10) * 100}%"></div>
          </div>
          <span class="report-category-value">${Number(value) || 0}</span>
        </div>`,
    )
    .join('')

  const answeredHtml =
    answeredQuestions.length > 0
      ? answeredQuestions
          .map(
            (item) => `
        <article class="message message-assistant">
          <header class="message-head">
            <span class="role">Question ${Number(item.question_number || 0)}</span>
          </header>
          <div class="message-body">
            <p><strong>Question:</strong> ${escapeHtml(item.question_text)}</p>
            <p><strong>Answer:</strong> ${escapeHtml(item.answer_text || '')}</p>
            ${
              item.feedback?.what_went_well
                ? `<p><strong>Well answered:</strong> ${escapeHtml(item.feedback.what_went_well)}</p>`
                : ''
            }
            ${(item.feedback?.improvements || [])
              .map(
                (improvement) =>
                  `<p><strong>Improvement:</strong> ${escapeHtml(improvement)}</p>`,
              )
              .join('')}
            ${(item.feedback?.missing_points || [])
              .map(
                (missing) =>
                  `<p><strong>Missing:</strong> ${escapeHtml(missing)}</p>`,
              )
              .join('')}
          </div>
        </article>`,
          )
          .join('\n')
      : '<p class="empty">No answers were recorded.</p>'

  const body = `
    <section class="conversation">
      <header class="conversation-head">
        <p class="doc-kicker">AI Mock Interview</p>
        <h2>Mock Interview Report</h2>
        <p class="doc-meta">Candidate: ${escapeHtml(
          candidateName || 'Unknown',
        )} · Resume: ${escapeHtml(resumeFilename || 'Not uploaded')} · Performance level: ${escapeHtml(
          level,
        )}</p>
      </header>
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Overall performance</span>
        </header>
        <div class="message-body">
          <p><strong>Score:</strong> ${score} / 10 · <strong>Performance level:</strong> ${escapeHtml(
            level,
          )}</p>
          <p><strong>Questions completed:</strong> ${Number(
            report?.questions_answered ?? answeredQuestions.length,
          )} / ${Number(report?.questions_total ?? 10)}</p>
          <p><strong>Answered questions:</strong> ${answeredNumbers.join(', ') || 'None'} · <strong>Unanswered:</strong> ${unansweredNumbers.join(', ') || 'None'}</p>
        </div>
      </article>
      ${
        Object.keys(categoryScores).length > 0
          ? `<div class="sources"><h3>Category scores</h3>${categoriesHtml}</div>`
          : ''
      }
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Strengths</span>
        </header>
        <div class="message-body">${
          strengths.length > 0
            ? strengths.map((strength) => `<p>${escapeHtml(strength)}</p>`).join('')
            : '<p class="empty">No strengths recorded.</p>'
        }</div>
      </article>
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Areas for improvement</span>
        </header>
        <div class="message-body">${
          areas.length > 0
            ? areas.map((area) => `<p>${escapeHtml(area)}</p>`).join('')
            : '<p class="empty">No improvement areas recorded.</p>'
        }</div>
      </article>
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Final feedback summary</span>
        </header>
        <div class="message-body">
          <p>${String(report?.summary || `${score} / 10`)
            .split('\n')
            .map((line) => escapeHtml(line))
            .join('<br>')}</p>
        </div>
      </article>
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Answered questions</span>
        </header>
        <div class="message-body">${answeredHtml}</div>
      </article>
      <article class="message message-assistant">
        <header class="message-head">
          <span class="role">Recommendations</span>
        </header>
        <div class="message-body">${
          recommendations.length > 0
            ? recommendations.map((item) => `<p>${escapeHtml(item)}</p>`).join('')
            : '<p class="empty">No specific recommendations were generated.</p>'
        }</div>
      </article>
    </section>`

  return documentShell({
    title: interviewReportFilename(candidateName, generatedAt).replace(/\.pdf$/i, ''),
    heading: 'Mock Interview Report',
    meta: `Score ${score} / 10 · ${level} · Generated ${formatExportTimestamp(generatedAt)}`,
    generated,
    body,
  })
}

export function buildHistoryPrintHtml({ conversations, generatedAt } = {}) {
  const list = Array.isArray(conversations) ? conversations : []
  const generated = formatGeneratedAt(generatedAt)
  const totalMessages = list.reduce(
    (total, conversation) =>
      total +
      (Array.isArray(conversation.messages) ? conversation.messages.length : 0),
    0,
  )

  const sections = list
    .map((conversation, index) => {
      const messages = Array.isArray(conversation.messages)
        ? conversation.messages
        : []
      const title =
        (conversation.title || 'Conversation').trim() || 'Conversation'
      const body =
        messages.length > 0
          ? messages.map((message) => messageHtml(message)).join('\n')
          : '<p class="empty">This conversation has no messages.</p>'

      return `<section class="conversation">
<header class="conversation-head">
<p class="doc-kicker">Conversation ${index + 1} of ${list.length}</p>
<h2>${escapeHtml(title)}</h2>
<p class="doc-meta">${messages.length} message${
        messages.length === 1 ? '' : 's'
      }</p>
</header>
${body}
</section>`
    })
    .join('\n')

  return documentShell({
    title: historyExportFilename(generatedAt).replace(/\.pdf$/i, ''),
    heading: 'Chat history',
    meta: `Generated ${generated} · ${list.length} conversation${
      list.length === 1 ? '' : 's'
    } · ${totalMessages} message${totalMessages === 1 ? '' : 's'}`,
    generated,
    body: sections || '<p class="empty">No conversations to export.</p>',
  })
}

export function openPrintDocument(html, title) {
  if (typeof window === 'undefined') return false

  const printWindow = window.open('', '_blank')
  if (!printWindow) return false

  printWindow.document.open()
  printWindow.document.write(html)
  printWindow.document.close()
  printWindow.document.title = String(title || 'conversation-export').replace(
    /\.pdf$/i,
    '',
  )

  const triggerPrint = () => {
    try {
      printWindow.focus()
      printWindow.print()
    } catch {
      printWindow.focus()
    }
  }

  if (printWindow.document.readyState === 'complete') {
    window.setTimeout(triggerPrint, 200)
  } else {
    printWindow.addEventListener(
      'load',
      () => window.setTimeout(triggerPrint, 200),
      { once: true },
    )
  }

  return true
}
