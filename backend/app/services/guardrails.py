"""Chat guardrails: input validation, intent classification, and fixed answers.

The first layer is deliberately lightweight (regex rules, no extra LLM call).
It distinguishes greetings, capability questions, prompt-injection attempts,
clearly unrelated requests, and questions that require recruitment evidence.

Only messages that the rules cannot place (not clearly recruitment, not clearly
off-topic) get one cheap LLM intent check. That check fails open: if the model
is unavailable or unconfigured, the message goes to the evidence-based pipeline
so legitimate recruiter questions are never blocked by mistake.
"""

import re

from pydantic import BaseModel

from app.rag.llm import LLMClient, load_llm_settings
from app.services.job_search_service import is_career_info_question, is_job_search

MAX_MESSAGE_LENGTH = 4_000
MAX_CONTROL_CHARS = 20

GREETING_PATTERN = re.compile(
    r"^(?:hi+|hello+|hey+(?:\s+there)?|good\s+(?:morning|afternoon|evening)|"
    r"thanks(?:\s+you)?|thank\s+you|how\s+are\s+you(?:\s+doing)?|what'?s\s+up|"
    r"howdy|greetings|yo)\b[\s!.?,]*$",
    re.IGNORECASE,
)

CAPABILITY_PATTERN = re.compile(
    r"\b(?:what\s+(?:can|do)\s+you\s+(?:do|help\s+with)|who\s+are\s+you|"
    r"what\s+are\s+your\s+(?:capabilities|features|abilities)|"
    r"how\s+(?:can|do)\s+you\s+help(?:\s+me)?|what\s+can\s+i\s+ask(?:\s+you)?|"
    r"what\s+do\s+you\s+support|tell\s+me\s+about\s+yourself|your\s+purpose)\b",
    re.IGNORECASE,
)

RECRUITMENT_PATTERN = re.compile(
    r"\b(?:resume|cv|candidate|candidates|job|jobs|skill|skills|experience|"
    r"hire|hiring|recruit|recruiter|recruitment|applicant|applicants|"
    r"shortlist|screening|screen|interview|interviews|requisition|vacancy|"
    r"opening|openings|position|onboarding|offer|qualification|qualifications|"
    r"education|employer|recruiting|staffing|payroll|document|documents|"
    r"job\s+description|job\s+requirement)\b",
    re.IGNORECASE,
)

INJECTION_PATTERN = re.compile(
    r"\b(?:ignore|disregard|forget|override|bypass)\s+(?:all\s+|any\s+|the\s+|"
    r"your\s+|these\s+|those\s+)*(?:previous|prior|above|earlier|system|safety|"
    r"developer|initial)\s+(?:instructions?|prompts?|rules?|messages?|"
    r"directives?|guidelines?)"
    r"|\b(?:reveal|print|show|repeat|output|leak)\s+(?:me\s+)?(?:your|the)\s+"
    r"(?:system\s+prompt|initial\s+instructions|hidden\s+prompt|instructions)"
    r"|\byou\s+are\s+now\s+(?:dan|an?\s+unrestricted|an?\s+unfiltered|"
    r"a\s+different\s+(?:ai|assistant|model))"
    r"|\b(?:act|behave)\s+as\s+(?:an?\s+)?(?:unrestricted|unfiltered|evil|"
    r"unlimited)\b|\bjailbreak\b",
    re.IGNORECASE,
)

OFF_TOPIC_PATTERNS = (
    re.compile(
        r"\b(?:weather|forecast|temperature|rain|snow|storm)\b|\bhow('?s| is)"
        r"\s+the\s+weather",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:football|soccer|cricket|basketball|nba|nfl|tennis|olympics)"
        r"\b|\bsports?\s+(?:score|news|update)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:movie|movies|film|netflix|song|lyrics|music|album|celebrity)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:recipe|cook|baking|bake|restaurant|pizza|pasta|dessert)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:joke|jokes|poem|poetry|story|stories|limerick|haiku|riddle)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:crypto|bitcoin|ethereum|stock\s+(?:price|market|tip)|"
        r"lottery|horoscope|casino|gambling|betting)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:capital\s+of|translate|weather\s+in|distance\s+between|"
        r"population\s+of)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:flight|flights|hotel|hotels|vacation|holiday\s+package|"
        r"tourist|tourism|visa\s+application\s+for\s+travel)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:diagnos(?:e|is)|symptoms?\s+of|medical\s+advice|prescription)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:write|generate|give\s+me)\s+(?:me\s+)?(?:a\s+)?"
        r"(?:code|program|script|essay|email\s+to\s+my\s+friend|love\s+letter)",
        re.IGNORECASE,
    ),
)

GREETING_ANSWER = (
    "Hello! I'm your recruiter AI assistant. I can answer questions about your "
    "uploaded documents, candidates, and jobs — for example: summarize a "
    "candidate, find who has specific skills, or explain a job's requirements. "
    "Ask me a recruitment question to get started."
)

CAPABILITY_ANSWER = (
    "I help your recruitment team by answering questions using only your own "
    "uploaded documents and records: summarize resumes, list candidates with "
    "specific skills, compare candidates to job requirements, and reference the "
    "exact sources for every answer. For recruitment-specific answers I need "
    "relevant uploaded or available recruitment information; if your documents "
    "do not contain the answer, I will tell you so instead of guessing."
)

OFF_TOPIC_ANSWER = (
    "That question is outside my purpose here. I'm a recruitment assistant: I "
    "can help with resumes, candidates, job requirements, matching, interview "
    "planning, and your uploaded recruitment documents. Try asking one of those."
)

INJECTION_ANSWER = (
    "I can't follow instructions that try to change my role, expose my "
    "configuration, or make me act outside recruitment work. I can still help "
    "with candidates, resumes, job requirements, matching, or interview "
    "planning from your own documents."
)

INSUFFICIENT_EVIDENCE_ANSWER = (
    "I could not find relevant information in your uploaded documents or "
    "recruitment records for this question. Upload or select the related "
    "documents and try again — I only answer from your own material and will "
    "not guess."
)


class _IntentVerdict(BaseModel):
    recruitment_related: bool


INTENT_SYSTEM_PROMPT = (
    "You classify one short user message for a recruitment assistant. "
    "Answer true when the message relates to recruitment work: candidates, "
    "resumes, jobs, hiring, interviews, offers, onboarding, salaries, notice "
    "periods, or the recruiter's own documents. Answer false only for clearly "
    "unrelated topics such as weather, sports, entertainment, cooking, travel, "
    "general trivia, or requests to write unrelated content. If conversation "
    "context shows the message answers a pending question (for example a "
    "location or role), judge it in that context. Return JSON only."
)


async def classify_unclear_message(
    text: str,
    client: LLMClient | None = None,
    context: str | None = None,
) -> bool | None:
    """Cheap LLM intent check for messages the regex rules cannot place.

    ``context`` (for example the pending assistant question) lets a short answer
    such as "Andhra Pradesh" be recognised as recruitment-related instead of an
    unrelated standalone message. Returns True for recruitment-related, False
    for clearly unrelated, and None when the model is unconfigured or fails so
    callers can fail open.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return None
    try:
        if client is None:
            settings = load_llm_settings()
            if not settings.configured:
                return None
            client = LLMClient(settings)
        client_settings = getattr(client, "settings", None)
        use_responses = bool(getattr(client_settings, "use_responses", False))
        message = f"Message:\n{cleaned}"
        if context and context.strip():
            message = (
                f"Conversation context (the user may be answering a pending question):\n"
                f"{context.strip()}\n\n{message}"
            )
        verdict = await client.complete_structured(
            _IntentVerdict,
            INTENT_SYSTEM_PROMPT,
            message,
            max_tokens=20,
            use_responses=use_responses,
        )
        return bool(verdict.recruitment_related)
    except Exception:
        return None


class MessageValidationError(ValueError):
    pass


def validate_message(text: str) -> str:
    """Validate a raw chat message and return the cleaned text."""
    cleaned = (text or "").strip()
    if not cleaned:
        raise MessageValidationError("Message cannot be empty.")
    if len(cleaned) > MAX_MESSAGE_LENGTH:
        raise MessageValidationError(
            f"Message is too long. Maximum length is {MAX_MESSAGE_LENGTH} characters."
        )
    control_chars = sum(1 for char in cleaned if ord(char) < 32 and char not in "\n\r\t")
    if control_chars > MAX_CONTROL_CHARS:
        raise MessageValidationError(
            "Message contains invalid control characters."
        )
    return cleaned


def classify_message(text: str) -> str:
    """Classify a cleaned chat message with regex rules only.

    Returns one of: "greeting", "injection", "capability", "job_search",
    "recruitment", "off_topic", "general". Recruitment keywords win over generic
    off-topic patterns so a message such as "translate this resume" is not blocked.
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return "general"

    if GREETING_PATTERN.match(cleaned):
        return "greeting"

    if INJECTION_PATTERN.search(cleaned):
        return "injection"

    if is_job_search(cleaned):
        return "job_search"

    if is_career_info_question(cleaned):
        return "career_info"

    if CAPABILITY_PATTERN.search(cleaned):
        return "capability"

    if RECRUITMENT_PATTERN.search(cleaned):
        return "recruitment"

    for pattern in OFF_TOPIC_PATTERNS:
        if pattern.search(cleaned):
            return "off_topic"

    return "general"
