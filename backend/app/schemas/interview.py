"""Pydantic schemas for mock interview sessions (Part 1 + Part 2)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

InterviewStatus = Literal["awaiting_resume", "ready", "in_progress", "completed"]

INTERVIEW_CATEGORIES = (
    "technical_knowledge",
    "problem_solving",
    "project_practical",
    "communication",
    "behavioural",
)

INTERVIEW_CATEGORY_WEIGHTS = {
    "technical_knowledge": 30,
    "problem_solving": 20,
    "project_practical": 20,
    "communication": 15,
    "behavioural": 15,
}


class InterviewDefaults(BaseModel):
    interview_type: str = "Technical + HR"
    total_questions: int = 10
    difficulty: str = "Adaptive"
    mode: str = "Text-based"


class InterviewExtractedInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_name: str | None = None
    job_title: str | None = None
    location: str | None = None
    email: str | None = None
    phone: str | None = None
    professional_summary: str | None = None
    total_experience: str | None = None
    technical_skills: list[str] = Field(default_factory=list)
    design_skills: list[str] = Field(default_factory=list)
    work_experience: list[dict[str, Any]] = Field(default_factory=list)
    internship_experience: list[dict[str, Any]] = Field(default_factory=list)
    projects: list[dict[str, Any]] = Field(default_factory=list)
    education: list[str] = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)
    achievements: list[str] = Field(default_factory=list)
    summary: str | None = None


class InterviewSessionResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID
    user_id: UUID
    document_id: UUID | None = None
    resume_filename: str | None = None
    candidate_role: str | None = None
    status: InterviewStatus
    interview_type: str
    difficulty: str
    mode: str
    current_question_number: int = 0
    total_questions: int = 10
    final_score: float | None = None
    evaluation_report: dict[str, Any] | None = None
    extracted_info: InterviewExtractedInfo | None = None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class InterviewFeedback(BaseModel):
    what_went_well: str = ""
    improvements: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)


class InterviewAnswerEvaluation(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=10.0)
    categories: dict[str, float] = Field(default_factory=dict)
    feedback: InterviewFeedback = Field(default_factory=InterviewFeedback)


class InterviewQuestion(BaseModel):
    question_number: int
    question_type: str = "technical"
    question_text: str
    difficulty: str = "Easy"


class InterviewQuestionsPayload(BaseModel):
    questions: list[InterviewQuestion] = Field(default_factory=list)


class InterviewQuestionResponse(BaseModel):
    question_number: int
    total_questions: int = 10
    question_type: str
    question_text: str
    difficulty: str = "Easy"
    answered: bool = False
    answer_text: str | None = None
    score: float | None = None
    feedback: InterviewFeedback | None = None
    answered_at: datetime | None = None


class InterviewStartResponse(BaseModel):
    session: InterviewSessionResponse
    questions: list[InterviewQuestionResponse] = Field(default_factory=list)
    message: str


class InterviewAnswerRequest(BaseModel):
    answer_text: str = ""


class InterviewAnswerResponse(BaseModel):
    question: InterviewQuestionResponse
    evaluation: InterviewAnswerEvaluation | None = None
    evaluation_error: str | None = None
    answered: bool = True
    advanced: bool = False
    next_question_number: int | None = None
    next_question_ready: bool = True
    evaluation_pending: bool = False


class InterviewCompleteReport(BaseModel):
    session_id: str
    status: str = "completed"
    score: float | None = None
    level: str = "Needs Improvement"
    questions_answered: int = 0
    questions_total: int = 10
    answered_question_numbers: list[int] = Field(default_factory=list)
    unanswered_question_numbers: list[int] = Field(default_factory=list)
    category_scores: dict[str, float] = Field(default_factory=dict)
    category_weights: dict[str, float] = Field(default_factory=dict)
    strengths: list[str] = Field(default_factory=list)
    areas_for_improvement: list[str] = Field(default_factory=list)
    answered_questions: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    completed_at: datetime | None = None
