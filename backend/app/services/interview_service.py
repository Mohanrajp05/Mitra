from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

from app.database import interview_queries
from app.database.connection import get_connection
from app.rag import resume_profile
from app.rag.interview_profile import extract_profile
from app.rag.llm import get_llm_client
from app.rag.vector_store import get_document_store
from app.schemas.interview import (
    INTERVIEW_CATEGORIES,
    InterviewAnswerEvaluation,
    InterviewCompleteReport,
    InterviewQuestion,
    InterviewQuestionsPayload,
)
from app.services import rag_service


class InterviewError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class InterviewSessionNotFoundError(InterviewError):
    pass


class InterviewQuestionNotFoundError(InterviewError):
    pass


class InterviewStateError(InterviewError):
    pass


INTERVIEW_TOTAL_QUESTIONS = 10

# Every candidate starts with the same deterministic opening question so the
# first question can be delivered immediately, without an LLM round trip.
INTERVIEW_FIRST_QUESTION = "Tell me about yourself."


INTERVIEW_DIFFICULTY_STEPS = (
    (1, 3, "Easy"),
    (4, 7, "Medium"),
    (8, 10, "Hard"),
)


def _difficulty_for_question(question_number: int) -> str:
    for first, last, difficulty in INTERVIEW_DIFFICULTY_STEPS:
        if first <= question_number <= last:
            return difficulty
    return "Hard"

INTERVIEW_CATEGORY_WEIGHTS = {
    "technical_knowledge": 30,
    "problem_solving": 20,
    "project_practical": 20,
    "communication": 15,
    "behavioural": 15,
}

_INTERVIEW_AREAS = (
    "self_introduction_background",
    "technical_skills_from_resume",
    "programming_technical_fundamentals",
    "project_explanation",
    "problem_solving_scenario",
    "internship_or_professional_experience",
    "role_specific_technical_depth",
    "practical_debugging_real_world_scenario",
    "teamwork_behavioural_skills",
    "career_goals_and_role_suitability",
)


def _get_session_or_404(user_id: str, session_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        session = interview_queries.get_session(connection, user_id, session_id)
    if session is None:
        raise InterviewSessionNotFoundError("Interview session not found.")
    return session


def create_session(user_id: str) -> dict[str, Any]:
    with get_connection() as connection:
        return interview_queries.create_session(connection, user_id)


def get_current_session(user_id: str) -> dict[str, Any] | None:
    with get_connection() as connection:
        return interview_queries.get_current_session(connection, user_id)


def get_session(user_id: str, session_id: str) -> dict[str, Any]:
    return _get_session_or_404(user_id, session_id)


def _interview_context(session: dict[str, Any]) -> dict[str, Any]:
    extracted = session.get("extracted_info") or {}
    if not isinstance(extracted, dict):
        extracted = {}

    def _entries(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)]

    work = _entries(extracted.get("work_experience"))
    internships = _entries(extracted.get("internship_experience"))

    def _project_text(item: dict[str, Any]) -> str:
        title = str(item.get("title") or "").strip()
        tech = ", ".join(str(t) for t in item.get("technologies") or [])
        parts = [title]
        if tech:
            parts.append(f"Technologies: {tech}")
        description = " ".join(str(d) for d in item.get("description") or []).strip()
        if description:
            parts.append(description[:400])
        return " - ".join(part for part in parts if part)

    return {
        "candidate_name": extracted.get("candidate_name")
        or session.get("resume_filename")
        or "the candidate",
        "candidate_role": session.get("candidate_role")
        or extracted.get("job_title")
        or "the target role",
        "location": extracted.get("location") or "",
        "email": extracted.get("email") or "",
        "interview_type": session.get("interview_type") or "Technical + HR",
        "difficulty": session.get("difficulty") or "Adaptive",
        "mode": session.get("mode") or "Text-based",
        "skills": [str(item) for item in extracted.get("technical_skills") or []],
        "design_skills": [str(item) for item in extracted.get("design_skills") or []],
        "experience": [
            " - ".join(
                part
                for part in (
                    f"{item.get('title') or ''} at {item.get('company') or ''}".strip(),
                    f"({item.get('period')})" if item.get("period") else "",
                    "; ".join(str(r) for r in item.get("responsibilities") or [])[:400],
                )
                if part
            )
            for item in work
            if item.get("title") or item.get("company")
        ],
        "internships": [
            f"{item.get('title') or ''} at {item.get('company') or ''} ({item.get('period') or ''}".strip()
            for item in internships
            if item.get("title") or item.get("company")
        ],
        "projects": [_project_text(item) for item in _entries(extracted.get("projects"))],
        "education": [str(item) for item in extracted.get("education") or []],
        "certifications": [str(item) for item in extracted.get("certifications") or []],
        "summary": str(extracted.get("professional_summary") or extracted.get("summary") or ""),
        "total_experience": extracted.get("total_experience") or "",
        "achievements": [str(item) for item in extracted.get("achievements") or []],
    }


def _llm_settings_kwargs() -> dict[str, Any]:
    client = get_llm_client()
    settings = getattr(client, "settings", None)
    use_responses = bool(getattr(settings, "use_responses", False))
    return {"use_responses": use_responses}


# Question generation is the slowest part of "Start Interview".  Generating the
# whole plan up front made the first question wait for all ten; instead we ask
# for Question 1 immediately and prepare the rest in the background.
QUESTION_GENERATION_TIMEOUT = 45.0


def _question_area(question_number: int) -> str:
    index = max(0, min(len(_INTERVIEW_AREAS) - 1, question_number - 1))
    return _INTERVIEW_AREAS[index]


def _opening_question() -> dict[str, Any]:
    """Question 1 is fixed for every candidate and needs no LLM call."""
    return {
        "question_number": 1,
        "question_type": "self_introduction",
        "question_text": INTERVIEW_FIRST_QUESTION,
        "difficulty": "Easy",
    }


def _question_prompts(
    context: dict[str, Any], numbers: list[int]
) -> tuple[str, str]:
    areas = "\n".join(
        f"- question_number {number}: area={_question_area(number)}, "
        f"difficulty={_difficulty_for_question(number)}"
        for number in numbers
    )
    system_prompt = (
        "You are the question generator of an AI mock interview for a recruitment team. "
        f"Generate exactly {len(numbers)} personalized interview questions based on the "
        "candidate's actual background. Questions must stay grounded in the candidate's "
        "stated skills, projects, experience and education. Never ask a candidate about "
        "experience they do not have. "
        'Return JSON only that matches this shape: '
        '{"questions": [{"question_number": 1, "question_type": "technical", '
        '"question_text": "string", "difficulty": "Easy"}]}. '
        "question_type must be one of: self_introduction, technical_skills, "
        "technical_fundamentals, project, problem_solving, experience, "
        "role_technical_depth, debugging, teamwork, career_goals. "
        "Each question_text must be a single, self-contained question that can be "
        "answered in a short paragraph. Use exactly the requested question_number values "
        "and the requested difficulty for each one."
    )
    user_prompt = (
        "Generate the requested mock interview questions for this candidate.\n"
        f"{json.dumps(context, default=str, ensure_ascii=False)}\n\n"
        f"Requested questions:\n{areas}"
    )
    return system_prompt, user_prompt


async def _generate_question_batch(
    context: dict[str, Any], numbers: list[int]
) -> list[dict[str, Any]]:
    """Generate a bounded set of interview questions in one LLM request."""
    ordered = sorted({int(number) for number in numbers})
    if not ordered:
        return []

    client = get_llm_client()
    system_prompt, user_prompt = _question_prompts(context, ordered)

    try:
        payload = await asyncio.wait_for(
            client.complete_structured(
                InterviewQuestionsPayload,
                system_prompt,
                user_prompt,
                temperature=0.2,
                **_llm_settings_kwargs(),
            ),
            timeout=QUESTION_GENERATION_TIMEOUT,
        )
    except asyncio.TimeoutError as exc:
        raise InterviewError(
            "The interview question generator took too long to respond."
        ) from exc

    by_number: dict[int, Any] = {}
    for item in payload.questions or []:
        try:
            number = int(item.question_number)
        except (TypeError, ValueError):
            continue
        by_number[number] = item

    questions: list[dict[str, Any]] = []
    for number in ordered:
        item = by_number.get(number)
        if item is None or not str(item.question_text or "").strip():
            raise InterviewError(
                "The interview question generator returned an incomplete question plan."
            )
        questions.append(
            {
                "question_number": number,
                "question_type": str(item.question_type or "technical"),
                "question_text": str(item.question_text).strip(),
                "difficulty": _difficulty_for_question(number),
            }
        )

    return questions


async def _generate_interview_questions(
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate the full ten-question plan (kept for the background prefetch)."""
    questions = await _generate_question_batch(
        context, list(range(1, INTERVIEW_TOTAL_QUESTIONS + 1))
    )
    if len(questions) != INTERVIEW_TOTAL_QUESTIONS:
        raise InterviewError(
            f"The interview question generator returned {len(questions)} questions; exactly "
            f"{INTERVIEW_TOTAL_QUESTIONS} are required."
        )
    return questions


def _list_question_rows(user_id: str, session_id: str) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return interview_queries.list_questions(connection, user_id, session_id)


def _store_questions(
    user_id: str, session_id: str, questions: list[dict[str, Any]]
) -> None:
    if not questions:
        return
    with get_connection() as connection:
        for question in questions:
            interview_queries.insert_question(
                connection, user_id, session_id, question
            )


def _missing_question_numbers(
    user_id: str, session_id: str, numbers: list[int]
) -> list[int]:
    rows = _list_question_rows(user_id, session_id)
    present = {int(row.get("question_number") or 0) for row in rows}
    return [number for number in numbers if number not in present]


# Strong references so background prefetch tasks are not garbage collected.
_PREFETCH_TASKS: dict[str, asyncio.Task] = {}


async def _prefetch_remaining_questions(
    user_id: str,
    session_id: str,
    document_id: str,
    context: dict[str, Any],
) -> None:
    """Generate questions 2-10 while the candidate answers Question 1."""
    started = time.perf_counter()
    try:
        numbers = list(range(2, INTERVIEW_TOTAL_QUESTIONS + 1))
        missing = await asyncio.to_thread(
            _missing_question_numbers, user_id, session_id, numbers
        )
        if not missing:
            return

        questions = await _generate_question_batch(context, missing)

        # Abort silently if the interview finished or the resume was replaced
        # while the request was in flight: never attach stale questions.
        current = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
        if str(current.get("document_id") or "") != document_id:
            return
        if current.get("status") not in {"ready", "in_progress"}:
            return

        await asyncio.to_thread(_store_questions, user_id, session_id, questions)
        logger.info(
            "interview prefetch session=%s generated=%d duration_ms=%d",
            session_id,
            len(questions),
            (time.perf_counter() - started) * 1000,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - prefetch is best effort
        logger.warning(
            "interview prefetch failed session=%s error=%s",
            session_id,
            type(exc).__name__,
        )


def _schedule_prefetch(
    user_id: str,
    session_id: str,
    document_id: str,
    context: dict[str, Any],
) -> None:
    if session_id in _PREFETCH_TASKS:
        return
    try:
        task = asyncio.create_task(
            _prefetch_remaining_questions(user_id, session_id, document_id, context)
        )
    except RuntimeError:  # no running loop (tests / sync callers)
        return
    _PREFETCH_TASKS[session_id] = task
    task.add_done_callback(lambda _task, sid=session_id: _PREFETCH_TASKS.pop(sid, None))


async def _ensure_question_available(
    user_id: str, session_id: str, number: int, session: dict[str, Any]
) -> None:
    """Guarantee the next question exists even if background prefetch failed."""
    missing = await asyncio.to_thread(
        _missing_question_numbers, user_id, session_id, [number]
    )
    if not missing:
        return
    if int(number) == 1:
        questions = [_opening_question()]
    else:
        started = time.perf_counter()
        questions = await _generate_question_batch(
            _interview_context(session), missing
        )
        logger.info(
            "interview next_question_generated session=%s number=%s duration_ms=%d",
            session_id,
            number,
            (time.perf_counter() - started) * 1000,
        )
    await asyncio.to_thread(_store_questions, user_id, session_id, questions)


def _question_rows_by_number(
    rows: list[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    return {int(row.get("question_number") or 0): row for row in rows}


def _set_current_question_number(
    user_id: str, session_id: str, number: int
) -> None:
    with get_connection() as connection:
        interview_queries.update_session(
            connection,
            user_id,
            session_id,
            {"current_question_number": number},
        )


async def _resolve_current_question(
    user_id: str, session_id: str, session: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the question awaiting an answer and keep the session pointer in sync.

    This is the single source of truth for interview progress.  It heals two
    inconsistent states that previously left the UI showing ``Question 2 of 10``
    with no question on screen:

    * ``current_question_number`` points at a question row that does not exist
      (for example when next-question generation failed after an answer was
      saved), and
    * questions exist but none of them is unanswered.
    """
    total = int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS)
    pointer = int(session.get("current_question_number") or 0)

    rows = await asyncio.to_thread(_list_question_rows, user_id, session_id)
    by_number = _question_rows_by_number(rows)

    pending = next(
        (
            number
            for number in sorted(by_number)
            if by_number[number].get("answered_at") is None
        ),
        None,
    )

    if pending is None:
        if not rows:
            number = 1
        else:
            highest = max(by_number)
            if highest >= total:
                return None
            number = max(pointer, highest + 1, 1)
            if number > total:
                return None
    else:
        number = pending

    if number not in by_number:
        await _ensure_question_available(user_id, session_id, number, session)
        rows = await asyncio.to_thread(_list_question_rows, user_id, session_id)
        by_number = _question_rows_by_number(rows)

    row = by_number.get(number)
    if row is None:
        return None

    if pointer != number:
        await asyncio.to_thread(
            _set_current_question_number, user_id, session_id, number
        )

    return row


_ANSWER_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "but", "if", "then", "than", "so", "as", "at",
        "by", "for", "from", "in", "into", "of", "on", "onto", "to", "up", "with", "out",
        "about", "just", "very", "too", "also", "not", "no", "nor", "is", "am", "are", "was",
        "were", "be", "been", "being", "have", "has", "had", "having", "do", "does", "did",
        "doing", "can", "could", "will", "would", "shall", "should", "may", "might", "must",
        "i", "me", "my", "mine", "we", "us", "our", "ours", "you", "your", "yours", "he", "him",
        "his", "she", "her", "it", "its", "they", "them", "their", "this", "that", "these",
        "those", "there", "here", "what", "which", "who", "whom", "how", "why", "when", "where",
        "dont", "cant", "wont", "isnt", "wasnt", "were", "idk",
    }
)

_MEANINGLESS_ANSWERS = frozenset(
    {
        "", "hi", "hii", "hiii", "hey", "heyy", "hello", "yo", "hiya", "howdy",
        "yes", "yeah", "yep", "yup", "no", "nope", "nah", "ok", "okay", "okay", "k", "kk",
        "sure", "fine", "good", "great", "nice", "cool", "awesome", "wow", "wait", "hmm",
        "hm", "mhm", "maybe", "perhaps", "possibly", "probably", "no idea", "not sure", "kind of",
        "sort of", "somewhat", "whatever", "anything", "nothing", "stuff", "test", "testing",
        "t", "asdf", "lol", "lmao", "true", "false", "correct", "wrong", "good morning",
        "good afternoon", "good evening", "good day", "no thanks", "no thank you", "thank you",
        "thanks", "bye", "see ya", "see you", "later", "np", "no problem", "perfect", "amazing",
        "excellent", "all the best", "good question", "interesting", "sure thing", "alright",
        "ok then", "i guess", "i think so", "hmm yes", "out of range", "out of scope", "out of bounds",
        "out of town", "lgtm", "smh", "brb", "gtg", "imo", "tbh", "rn",
    }
)


def _is_meaningless_answer(answer: str) -> bool:
    """Return True for empty / greeting / acknowledgement / filler answers."""
    text = re.sub(r"\s+", " ", (answer or "").strip()).strip().lower()
    if not text or text in _MEANINGLESS_ANSWERS:
        return True
    tokens = [token for token in re.split(r"[^a-z0-9]+", text) if token]
    content = [token for token in tokens if token not in _ANSWER_STOPWORDS and token not in _MEANINGLESS_ANSWERS]
    return len(content) < 2


def _clamp_categories(raw: Any) -> dict[str, float]:
    """Clamp LLM category subscores to the documented 0-10 range."""
    source = raw if isinstance(raw, dict) else {}
    clamped: dict[str, float] = {}
    for category in INTERVIEW_CATEGORIES:
        try:
            value = float(source.get(category) or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        clamped[category] = round(min(10.0, max(0.0, value)), 2)
    return clamped


def _score_from_categories(
    categories: dict[str, Any],
    weights: dict[str, float] | None = None,
) -> float:
    """Deterministic weighted score (0-100) from 0-10 category subscores."""
    weight_map = dict(weights or INTERVIEW_CATEGORY_WEIGHTS)
    weight_total = sum(float(weight) for weight in weight_map.values()) or 1.0
    weighted_sum = sum(
        float(weight_map.get(category, 0.0)) * float(categories.get(category) or 0.0)
        for category in INTERVIEW_CATEGORIES
    )
    score = weighted_sum / weight_total
    return round(min(10.0, max(0.0, score)), 2)


def _final_interview_score(
    answered_rows: list[dict[str, Any]],
) -> tuple[float, dict[str, float]]:
    """Aggregate answered evaluations into the final interview score (0-10).

    Formula (documented):
        per_question[c] = weighted average of the category subscores for one
                           answered question (subscores are 0-10).
        final_score     = mean(per_question over all answered questions).
        category[c]     = mean of category subscores over answered questions.

    The overall score is derived from the individual question evaluations with a
    deterministic formula and is expressed on the same 0-10 scale as the category
    subscores, so the report can never mix scales.
    """
    per_question_scores: list[float] = []
    subscores: dict[str, list[float]] = {category: [] for category in INTERVIEW_CATEGORIES}
    for row in sorted(answered_rows, key=lambda item: int(item.get("question_number") or 0)):
        evaluation = row.get("evaluation") if isinstance(row, dict) else None
        evaluation_map = evaluation if isinstance(evaluation, dict) else {}
        categories = _clamp_categories(evaluation_map.get("categories"))
        per_question_scores.append(_score_from_categories(categories, INTERVIEW_CATEGORY_WEIGHTS))
        for category in INTERVIEW_CATEGORIES:
            subscores[category].append(float(categories.get(category) or 0.0))

    final_score = round(sum(per_question_scores) / len(per_question_scores), 2) if per_question_scores else 0.0
    category_scores: dict[str, float] = {}
    for category in INTERVIEW_CATEGORIES:
        values = subscores.get(category) or []
        average = sum(values) / len(values) if values else 0.0
        category_scores[category] = round(min(10.0, max(0.0, average)), 2)
    return round(min(10.0, max(0.0, final_score)), 2), category_scores


def _build_interview_summary(
    final_score: float,
    answered_rows: list[dict[str, Any]],
    strengths: list[str],
    areas_for_improvement: list[str],
    recommendations: list[str],
) -> str:
    """Build the final interview feedback summary (max 6 lines)."""
    answered = [row for row in answered_rows if row.get("answered_at") is not None]
    answeredCount = len(answered)
    unansweredCount = max(0, INTERVIEW_TOTAL_QUESTIONS - answeredCount)
    correctCount = sum(
        1
        for row in answered
        if float(((row.get("evaluation") or {}).get("score")) or 0.0) > 0.0
    )
    incorrectOrUnanswered = max(0, INTERVIEW_TOTAL_QUESTIONS - correctCount)

    strongest = str(strengths[0]) if strengths else "No single area stood out; consistent effort was shown."
    mainImprovement = str(areas_for_improvement[0]) if areas_for_improvement else "Provide fuller answers with concrete examples."
    finalRecommendation = str(recommendations[0]) if recommendations else "Practice timed mock interviews with real project examples."

    return "\n".join(
        [
            f"Overall score: {final_score}/10.",
            f"Correct answers: {correctCount}/10.",
            f"Incorrect or unanswered: {incorrectOrUnanswered}/10.",
            f"Strongest area: {strongest}",
            f"Main improvement area: {mainImprovement}",
            f"Final recommendation: {finalRecommendation}",
        ]
    )


def _meaningless_answer_evaluation(question_text: str = "") -> dict[str, Any]:
    """Deterministic, low-scoring evaluation for empty / meaningless answers."""
    focus = f" for this question: \"{question_text}\"" if question_text else ""
    return {
        "score": 0.0,
        "categories": {category: 0.0 for category in INTERVIEW_CATEGORIES},
        "feedback": {
            "what_went_well": "",
            "improvements": [
                "The submitted answer was too short, vague or off-topic"
                + focus
                + " to demonstrate competency; a relevant answer would describe a concrete example with context, action and outcome."
            ],
            "missing_points": [
                "The answer lacked substantive content, so technical correctness, depth, practical reasoning and communication clarity could not be evaluated."
            ],
        },
    }


async def _evaluate_interview_answer(
    context: dict[str, Any],
    question: dict[str, Any],
    answer: str,
) -> dict[str, Any]:
    client = get_llm_client()
    answer_text = (answer or "").strip()

    if _is_meaningless_answer(answer_text):
        # Deterministic guard: greetings / filler / acknowledgement answers are
        # never sent to the LLM for scoring and can never receive a positive
        # technical score.
        return _meaningless_answer_evaluation(str(question.get("question_text") or ""))

    system_prompt = (
        "You are an interviewer evaluating a mock interview answer with a consistent rubric. "
        "Score the answer 0-100. Score each category 0-10: technical_knowledge, problem_solving, "
        "project_practical, communication, behavioural. Provide feedback with what_went_well, "
        "improvements and missing_points. Do not reveal the ideal answer before the candidate "
        "responds. Do not award marks merely for using technical keywords. Do not disproportionately "
        "penalize grammar or spelling when the technical meaning is clear. Return JSON only that "
        "matches this shape: "
        '{"score": 0, "categories": {"technical_knowledge": 0, "problem_solving": 0, "project_practical": 0, "communication": 0, "behavioural": 0}, "feedback": {"what_went_well": "", "improvements": [], "missing_points": []}}.'
    )
    user_prompt = (
        "Evaluate this mock interview answer.\n"
        f"{json.dumps(context, default=str, ensure_ascii=False)}\n\n"
        f"Question: {question.get('question_text')}\n"
        f"Answer: {answer_text}"
    )

    evaluation = await client.complete_structured(
        InterviewAnswerEvaluation,
        system_prompt,
        user_prompt,
        temperature=0.0,
        **_llm_settings_kwargs(),
    )

    categories = _clamp_categories(getattr(evaluation, "categories", None))
    score = _score_from_categories(categories, INTERVIEW_CATEGORY_WEIGHTS)
    feedback_model = getattr(evaluation, "feedback", None)
    feedback_map: dict[str, Any] = (
        feedback_model.model_dump() if feedback_model is not None else {}
    )
    what_went_well = str(feedback_map.get("what_went_well") or "").strip()
    improvements = [
        str(item) for item in (feedback_map.get("improvements") or []) if str(item).strip()
    ]
    missing_points = [
        str(item) for item in (feedback_map.get("missing_points") or []) if str(item).strip()
    ]

    return {
        "score": score,
        "categories": categories,
        "feedback": {
            "what_went_well": what_went_well,
            "improvements": improvements,
            "missing_points": missing_points,
        },
    }


def _performance_level(score: float) -> str:
    if score >= 8.5:
        return "Excellent"
    if score >= 7.0:
        return "Good"
    if score >= 5.0:
        return "Average"
    return "Needs Improvement"


def _question_response(
    row: dict[str, Any] | None, total_questions: int = INTERVIEW_TOTAL_QUESTIONS
) -> dict[str, Any]:
    if row is None:
        raise InterviewQuestionNotFoundError("Interview question not found.")

    answered_at = row.get("answered_at")
    evaluation = row.get("evaluation")
    evaluation_map = evaluation if isinstance(evaluation, dict) else None
    feedback_map = evaluation_map.get("feedback") if evaluation_map else None
    categories = evaluation_map.get("categories") if evaluation_map else None

    return {
        "question_number": int(row.get("question_number") or 0),
        "total_questions": int(total_questions or INTERVIEW_TOTAL_QUESTIONS),
        "question_type": str(row.get("question_type") or "technical"),
        "question_text": str(row.get("question_text") or ""),
        "difficulty": str(row.get("difficulty") or _difficulty_for_question(int(row.get("question_number") or 1))),
        "answered": bool(answered_at),
        "answer_text": row.get("answer_text"),
        "score": float(evaluation_map.get("score") or 0.0) if evaluation_map else None,
        "feedback": {
            "what_went_well": str(feedback_map.get("what_went_well") or "") if isinstance(feedback_map, dict) else "",
            "improvements": [str(item) for item in (feedback_map.get("improvements") or []) if item] if isinstance(feedback_map, dict) else [],
            "missing_points": [str(item) for item in (feedback_map.get("missing_points") or []) if item] if isinstance(feedback_map, dict) else [],
        },
        "answered_at": answered_at,
    }


async def start_session(user_id: str, session_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") == "completed":
        raise InterviewStateError("This interview session is already completed.")
    if session.get("status") not in {"ready", "in_progress"}:
        raise InterviewStateError("Upload and process a resume before starting the interview.")

    document_id = str(session.get("document_id") or "")
    context = _interview_context(session)

    # Question 1 is deterministic and stored before any LLM work, so the
    # candidate always receives it even if the provider is slow or down.
    existing = await asyncio.to_thread(_list_question_rows, user_id, session_id)
    if 1 not in _question_rows_by_number(existing):
        await asyncio.to_thread(
            _store_questions, user_id, session_id, [_opening_question()]
        )

    current = await _resolve_current_question(user_id, session_id, session)
    if current is None:
        raise InterviewStateError(
            "All interview questions have been answered. Complete the interview to view your report."
        )
    current_number = int(current.get("question_number") or 1)

    with get_connection() as connection:
        updated = interview_queries.update_session(
            connection,
            user_id,
            session_id,
            {
                "status": "in_progress",
                "current_question_number": current_number,
                "total_questions": INTERVIEW_TOTAL_QUESTIONS,
            },
        )

    if updated is None:
        raise InterviewSessionNotFoundError("Interview session not found.")

    # Prepare questions 2-10 while the candidate answers Question 1.
    _schedule_prefetch(user_id, session_id, document_id, context)

    stored_questions = await asyncio.to_thread(
        _list_question_rows, user_id, session_id
    )
    question_responses = [
        _question_response(stored, INTERVIEW_TOTAL_QUESTIONS)
        for stored in stored_questions
    ]

    logger.info(
        "interview started session=%s current_question=%s questions_returned=%d duration_ms=%d",
        session_id,
        current_number,
        len(question_responses),
        (time.perf_counter() - started) * 1000,
    )

    return {
        "session": updated,
        "questions": question_responses,
        "message": "Interview session started.",
    }


async def get_current_question(user_id: str, session_id: str) -> dict[str, Any]:
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") != "in_progress":
        raise InterviewStateError(
            "The interview is not in progress. Start the interview first."
        )

    question = await _resolve_current_question(user_id, session_id, session)
    if question is None:
        raise InterviewStateError(
            "All interview questions have been answered. Complete the interview to view your report."
        )

    response = _question_response(question, int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS))
    response["current"] = True
    response["status"] = session.get("status")
    return response


async def list_questions_for_session(
    user_id: str, session_id: str
) -> list[dict[str, Any]]:
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    with get_connection() as connection:
        rows = interview_queries.list_questions(connection, user_id, session_id)
    total = int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS)
    return [_question_response(row, total) for row in rows]


_PENDING_EVALUATIONS: dict[str, set[asyncio.Task]] = {}


def _has_running_loop() -> bool:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _session_has_pending_evaluations(session_id: str) -> bool:
    return bool(_PENDING_EVALUATIONS.get(session_id))


def _store_evaluation(
    user_id: str,
    session_id: str,
    question_number: int,
    evaluation: dict[str, Any],
) -> None:
    with get_connection() as connection:
        interview_queries.update_question_evaluation(
            connection, user_id, session_id, question_number, evaluation
        )


async def _run_evaluation(
    user_id: str,
    session_id: str,
    question_number: int,
    context: dict[str, Any],
    question: dict[str, Any],
    answer: str,
) -> None:
    started = time.perf_counter()
    try:
        evaluation = await _evaluate_interview_answer(context, question, answer)
        await asyncio.to_thread(
            _store_evaluation, user_id, session_id, question_number, evaluation
        )
        logger.info(
            "interview evaluation session=%s question=%s duration_ms=%d",
            session_id,
            question_number,
            (time.perf_counter() - started) * 1000,
        )
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - scored again at completion
        logger.warning(
            "interview evaluation failed session=%s question=%s error=%s",
            session_id,
            question_number,
            type(exc).__name__,
        )


def _schedule_evaluation(
    user_id: str,
    session_id: str,
    question_number: int,
    context: dict[str, Any],
    question: dict[str, Any],
    answer: str,
) -> None:
    task = asyncio.create_task(
        _run_evaluation(
            user_id, session_id, question_number, context, question, answer
        )
    )
    _PENDING_EVALUATIONS.setdefault(session_id, set()).add(task)

    def _done(finished: asyncio.Task, sid: str = session_id) -> None:
        bucket = _PENDING_EVALUATIONS.get(sid)
        if bucket is not None:
            bucket.discard(finished)
            if not bucket:
                _PENDING_EVALUATIONS.pop(sid, None)

    task.add_done_callback(_done)


async def _await_pending_evaluations(
    session_id: str, timeout: float = 120.0
) -> None:
    tasks = list(_PENDING_EVALUATIONS.get(session_id) or ())
    if not tasks:
        return
    try:
        await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
        )
    except asyncio.TimeoutError:
        logger.warning(
            "interview evaluation wait timed out session=%s pending=%d",
            session_id,
            len(tasks),
        )


async def submit_answer(
    user_id: str,
    session_id: str,
    question_number: int,
    answer_text: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") != "in_progress":
        raise InterviewStateError("The interview is not in progress.")

    current_number = int(session.get("current_question_number") or 1)
    if question_number != current_number:
        raise InterviewStateError(
            "You can only answer the current interview question in order."
        )

    with get_connection() as connection:
        question = interview_queries.get_question(
            connection, user_id, session_id, question_number
        )

    if question is None:
        raise InterviewQuestionNotFoundError("This interview question was not found.")

    response = _question_response(question, int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS))
    if response["answered"]:
        raise InterviewStateError(
            "This interview question has already been answered."
        )

    answer = (answer_text or "").strip()
    if not answer:
        raise InterviewStateError("The answer cannot be empty.")

    with get_connection() as connection:
        updated_question = interview_queries.update_question_answer(
            connection,
            user_id,
            session_id,
            question_number,
            answer_text=answer,
        )

    evaluation: dict[str, Any] | None = None
    evaluation_error: str | None = None
    evaluation_pending = False
    context = _interview_context(session)

    if _session_has_pending_evaluations(session_id) or not _has_running_loop():
        # Preserve strict ordering when several answers are being evaluated.
        try:
            evaluation = await _evaluate_interview_answer(context, response, answer)
            with get_connection() as connection:
                interview_queries.update_question_evaluation(
                    connection,
                    user_id,
                    session_id,
                    question_number,
                    evaluation,
                )
        except Exception as exc:  # noqa: BLE001 - never lose the saved answer
            evaluation_error = f"{type(exc).__name__}: {exc}"
    else:
        # Evaluation is not needed to show the next question.  Run it in the
        # background so the candidate can keep answering; the final report
        # waits for these tasks before scoring.
        _schedule_evaluation(
            user_id, session_id, question_number, context, response, answer
        )
        evaluation_pending = True

    with get_connection() as connection:
        final_question = interview_queries.get_question(
            connection, user_id, session_id, question_number
        )

    advanced = question_number < int(
        session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS
    )
    next_number = question_number + 1 if advanced else None

    next_question_ready = True
    if advanced:
        # The background prefetch normally already stored this question.  A
        # generation failure must not invalidate the saved answer, and the
        # session pointer must never move to a question that does not exist.
        try:
            await _ensure_question_available(user_id, session_id, next_number, session)
        except Exception as exc:  # noqa: BLE001 - answer is already persisted
            next_question_ready = False
            logger.warning(
                "interview next_question_failed session=%s number=%s error=%s",
                session_id,
                next_number,
                type(exc).__name__,
            )
        else:
            next_question_ready = not await asyncio.to_thread(
                _missing_question_numbers, user_id, session_id, [next_number]
            )

        if next_question_ready:
            # Advance only now: the next question is persisted and deliverable.
            with get_connection() as connection:
                interview_queries.update_session(
                    connection,
                    user_id,
                    session_id,
                    {"current_question_number": next_number},
                )
        else:
            # Keep the interview resumable: the pointer stays on the answered
            # question and _resolve_current_question regenerates the next one
            # on the following request.
            logger.warning(
                "interview progression_paused session=%s next_number=%s",
                session_id,
                next_number,
            )

    logger.info(
        "interview answer session=%s question=%s evaluation_pending=%s evaluation_error=%s duration_ms=%d",
        session_id,
        question_number,
        evaluation_pending,
        bool(evaluation_error),
        (time.perf_counter() - started) * 1000,
    )

    return {
        "question": _question_response(
            final_question, int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS)
        ),
        "evaluation": evaluation,
        "evaluation_error": evaluation_error,
        "answered": True,
        "advanced": advanced,
        "next_question_number": next_number,
        "next_question_ready": next_question_ready,
        "evaluation_pending": evaluation_pending,
    }


async def complete_interview(user_id: str, session_id: str) -> dict[str, Any]:
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") == "completed":
        raise InterviewStateError("This interview session has already been completed.")
    if session.get("status") != "in_progress":
        raise InterviewStateError(
            "The interview must be completed from an in-progress session."
        )

    await _await_pending_evaluations(session_id)

    with get_connection() as connection:
        rows = interview_queries.list_questions(connection, user_id, session_id)

    # Any answer whose background evaluation failed must still be scored; never
    # fabricate a zero for a real answer.
    missing_evaluations = [
        row
        for row in rows
        if row.get("answered_at") is not None and not row.get("evaluation")
    ]
    evaluation_context: dict[str, Any] | None = None
    for row in missing_evaluations:
        try:
            if evaluation_context is None:
                evaluation_context = _interview_context(session)
            number = int(row.get("question_number") or 0)
            evaluation = await _evaluate_interview_answer(
                evaluation_context,
                _question_response(
                    row,
                    int(session.get("total_questions") or INTERVIEW_TOTAL_QUESTIONS),
                ),
                str(row.get("answer_text") or ""),
            )
            await asyncio.to_thread(
                _store_evaluation, user_id, session_id, number, evaluation
            )
        except Exception as exc:  # noqa: BLE001 - report what we do have
            logger.warning(
                "interview evaluation backfill failed session=%s question=%s error=%s",
                session_id,
                row.get("question_number"),
                type(exc).__name__,
            )

    if missing_evaluations:
        with get_connection() as connection:
            rows = interview_queries.list_questions(connection, user_id, session_id)

    answered_rows = [row for row in rows if row.get("answered_at") is not None]
    unanswered_rows = [row for row in rows if row.get("answered_at") is None]

    final_score, category_scores = _final_interview_score(answered_rows)
    level = _performance_level(final_score)

    answered_numbers = [int(row.get("question_number") or 0) for row in answered_rows]
    unanswered_numbers = [int(row.get("question_number") or 0) for row in unanswered_rows]

    strengths: list[str] = []
    areas_for_improvement: list[str] = []
    answered_questions: list[dict[str, Any]] = []
    recommendations: list[str] = []

    for row in answered_rows:
        evaluation = row.get("evaluation") or {}
        evaluation_map = evaluation if isinstance(evaluation, dict) else {}
        categories = evaluation_map.get("categories") or {}
        feedback_map = evaluation_map.get("feedback") or {}
        what_went_well = str(feedback_map.get("what_went_well") or "").strip()
        improvements = [str(item) for item in feedback_map.get("improvements") or [] if item]
        missing_points = [str(item) for item in feedback_map.get("missing_points") or [] if item]

        if what_went_well and what_went_well not in strengths:
            strengths.append(what_went_well)

        for item in improvements:
            if item and item not in areas_for_improvement:
                areas_for_improvement.append(item)
        for item in missing_points:
            if item and item not in areas_for_improvement:
                areas_for_improvement.append(item)

        answered_questions.append(
            {
                "question_number": int(row.get("question_number") or 0),
                "question_text": str(row.get("question_text") or ""),
                "answer_text": str(row.get("answer_text") or ""),
                "score": float(evaluation_map.get("score") or 0.0),
                "categories": categories if isinstance(categories, dict) else {},
                "feedback": {
                    "what_went_well": what_went_well,
                    "improvements": improvements,
                    "missing_points": missing_points,
                },
            }
        )

    recommendations = [
        f"Targeted improvement: {item}" for item in missing_points if item
    ][:8]

    report = {
        "session_id": str(session.get("id") or session_id),
        "status": "completed",
        "score": final_score,
        "level": level,
        "questions_answered": len(answered_rows),
        "questions_total": len(rows) or INTERVIEW_TOTAL_QUESTIONS,
        "answered_question_numbers": answered_numbers,
        "unanswered_question_numbers": unanswered_numbers,
        "category_scores": category_scores,
        "category_weights": dict(INTERVIEW_CATEGORY_WEIGHTS),
        "strengths": strengths,
        "areas_for_improvement": areas_for_improvement,
        "answered_questions": answered_questions,
        "recommendations": recommendations,
        "summary": _build_interview_summary(
            final_score, answered_rows, strengths, areas_for_improvement, recommendations
        ),
        "completed_at": session.get("completed_at")
        or datetime.now(timezone.utc).isoformat(),
    }

    with get_connection() as connection:
        updated = interview_queries.update_session(
            connection,
            user_id,
            session_id,
            {
                "status": "completed",
                "final_score": final_score,
                "evaluation_report": report,
                "completed_at": report["completed_at"],
            },
        )

    if updated is None:
        raise InterviewSessionNotFoundError("Interview session not found.")

    return report


def _looks_like_name(line: str) -> bool:
    cleaned = re.sub(r"\s+", " ", (line or "").strip())
    if not cleaned or len(cleaned) > 60 or len(cleaned) < 3:
        return False
    if "@" in cleaned or any(ch.isdigit() for ch in cleaned):
        return False
    if any(ch in cleaned for ch in ":|/\\[]{}()"):
        return False
    words = cleaned.split()
    if not 2 <= len(words) <= 5:
        return False
    if sum(1 for ch in cleaned if ch.isalpha()) < 4:
        return False
    return all(re.fullmatch(r"[A-Za-z][A-Za-z'.-]*", word) for word in words)


def _extract_candidate_name(text: str) -> str | None:
    for raw in (text or "").splitlines()[:12]:
        line = raw.strip()
        if not line or resume_profile._match_header(line):
            continue
        if _looks_like_name(line):
            return line[:120]
    return None


def _dedupe_lines(values: list[str], limit: int) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value or "").strip())
        if not cleaned:
            continue
        key = cleaned.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(cleaned[:300])
        if len(result) >= limit:
            break
    return result


def _split_experience(entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    work: list[dict[str, Any]] = []
    internships: list[dict[str, Any]] = []
    for entry in entries or []:
        title = str(entry.get("title") or "").strip()
        company = str(entry.get("company") or "").strip()
        item = {"title": title or None, "company": company or None, "period": entry.get("period")}
        if "intern" in f"{title} {company}".casefold():
            internships.append(item)
        else:
            work.append(item)
    return work[:20], internships[:20]


def _extract_projects(text: str) -> list[str]:
    project_headers = {"projects", "project experience", "personal projects", "academic projects"}
    lines = (text or "").replace("\r\n", "\n").split("\n")
    current = None
    collected: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        lower = stripped.rstrip(":").strip().lower()
        header = resume_profile._match_header(stripped)
        if header:
            current = header[0]
            rest = (header[1] or "").strip()
            if lower in project_headers and rest:
                collected.append(rest)
            continue
        if lower in project_headers:
            current = "projects"
            continue
        if current == "projects" or current in project_headers:
            collected.append(resume_profile._clean_line(stripped))
    return _dedupe_lines(collected, 20)


def _extract_responsibilities(text: str) -> list[str]:
    aliases = {"responsibilities", "roles and responsibilities", "key responsibilities"}
    lines = (text or "").replace("\r\n", "\n").split("\n")
    current = None
    collected: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            continue
        lower = stripped.rstrip(":").strip().lower()
        header = resume_profile._match_header(stripped)
        if lower in aliases:
            current = "responsibilities"
            continue
        if header:
            current = header[0]
            continue
        if current == "responsibilities":
            collected.append(resume_profile._clean_line(stripped))
    return _dedupe_lines(collected, 20)


def extract_interview_info(document_text: str) -> dict[str, Any]:
    profile = extract_profile(document_text)
    profile["summary"] = profile.get("professional_summary")
    return profile


def _document_text(owner_user_id: str, document_id: str) -> str:
    """Read the original uploaded file with the same loader used at upload.

    Stored chunks overlap and are trimmed, so joining them inserts artificial
    line breaks and splits words mid-token.  Re-loading the original document
    preserves reading order, headings and wrapped lines exactly.

    The extracted text is cached by content hash, so the upload path and the
    interview path share a single parse of the same file.
    """
    from app.rag import document_cache
    from app.rag.config import rag_settings
    from app.rag.document_loader import load_document

    store = get_document_store()
    record = None
    get_document = getattr(store, "get_document", None)
    if callable(get_document):
        try:
            record = get_document(owner_user_id, document_id)
        except Exception:  # noqa: BLE001 - fall back to the original file
            record = None
    if record is None and not hasattr(store, "open_original"):
        raise InterviewStateError("The uploaded resume could not be found.")

    content_hash = getattr(record, "content_hash", None)
    cached = document_cache.get_document_text(content_hash)
    if cached:
        return cached

    original = store.open_original(owner_user_id, document_id)
    if original is None:
        raise InterviewStateError("The uploaded resume could not be found.")
    path, mime_type, filename = original
    try:
        loaded = load_document(
            filename=filename,
            data=path.read_bytes(),
            max_bytes=rag_settings.max_upload_bytes,
            max_chars=rag_settings.max_text_chars,
            content_type=mime_type,
        )
    except Exception as exc:  # noqa: BLE001 - normalise loader failures
        raise InterviewStateError(f"The uploaded resume could not be read: {exc}") from exc
    text = (loaded.text or "").strip()
    if not text:
        raise InterviewStateError("No readable text was found in the uploaded resume.")
    document_cache.set_document_text(content_hash or loaded.content_hash, text)
    return text


async def attach_resume(
    user_id: str,
    session_id: str,
    *,
    filename: str,
    data: bytes,
    content_type: str | None = None,
) -> dict[str, Any]:
    from app.rag import document_cache

    started = time.perf_counter()
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") == "completed":
        raise InterviewStateError("This interview session is already completed.")

    previous_document_id = session.get("document_id")

    record = await rag_service.save_document(
        user_id,
        filename=filename,
        data=data,
        source_type="resume",
        content_type=content_type,
    )
    stored_at = time.perf_counter()
    summary = record.summary() if hasattr(record, "summary") else dict(record)
    document_id = str(summary.get("document_id") or "")
    resume_filename = str(summary.get("filename") or filename or "")
    content_hash = str(summary.get("content_hash") or "") or None

    # Reuse the text produced during upload; only re-parse on a cache miss.
    document_text = await asyncio.to_thread(_document_text, user_id, document_id)
    text_ready = time.perf_counter()
    extracted = await asyncio.to_thread(
        document_cache.get_or_extract_profile,
        content_hash,
        extract_interview_info,
        document_text,
    )
    profile_ready = time.perf_counter()

    changes = {
        "document_id": document_id,
        "resume_filename": resume_filename,
        "extracted_info": extracted,
        "status": "ready",
        "current_question_number": 0,
    }
    remaining_previous = 0
    with get_connection() as connection:
        # A replacement invalidates questions/answers generated from the old resume.
        interview_queries.delete_questions(connection, user_id, session_id)
        updated = interview_queries.update_session(connection, user_id, session_id, changes)
        if previous_document_id and str(previous_document_id) != document_id:
            remaining_previous = interview_queries.count_document_references(
                connection, user_id, str(previous_document_id)
            )
    persisted_at = time.perf_counter()

    if updated is None:
        raise InterviewSessionNotFoundError("Interview session not found.")

    if remaining_previous == 0 and previous_document_id and str(previous_document_id) != document_id:
        try:
            await rag_service.delete_document(user_id, str(previous_document_id))
        except Exception:  # noqa: BLE001 - cleanup is best-effort
            pass

    logger.info(
        "interview resume_attached session=%s store_ms=%d text_ms=%d profile_ms=%d persist_ms=%d total_ms=%d",
        session_id,
        (stored_at - started) * 1000,
        (text_ready - stored_at) * 1000,
        (profile_ready - text_ready) * 1000,
        (persisted_at - profile_ready) * 1000,
        (time.perf_counter() - started) * 1000,
    )

    return updated


async def remove_resume(user_id: str, session_id: str) -> dict[str, Any]:
    """Detach the resume from a session so a new one can be uploaded."""
    session = await asyncio.to_thread(_get_session_or_404, user_id, session_id)
    if session.get("status") == "completed":
        raise InterviewStateError("This interview session is already completed.")
    if session.get("status") == "in_progress":
        raise InterviewStateError(
            "Finish the current interview before removing the resume."
        )

    document_id = session.get("document_id")
    if not document_id:
        return session

    document_id = str(document_id)
    with get_connection() as connection:
        updated = interview_queries.update_session(
            connection,
            user_id,
            session_id,
            {
                "document_id": None,
                "resume_filename": None,
                "extracted_info": None,
                "status": "awaiting_resume",
            },
        )
        remaining = interview_queries.count_document_references(
            connection, user_id, document_id
        )

    if updated is None:
        raise InterviewSessionNotFoundError("Interview session not found.")

    # Delete the stored file only when no other interview session still uses it.
    if remaining == 0:
        try:
            await rag_service.delete_document(user_id, document_id)
        except Exception:  # noqa: BLE001 - detach must still succeed
            pass

    return updated
