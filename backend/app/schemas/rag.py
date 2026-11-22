from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SourceType = Literal["resume", "job_description", "knowledge"]
DraftType = Literal["interview_invitation", "follow_up", "application_status"]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    document_id: str
    owner_user_id: str
    source_type: SourceType
    candidate_id: str | None = None
    job_id: str | None = None
    filename: str
    mime_type: str
    byte_size: int
    content_hash: str
    embedding_model: str
    embedding_dimension: int
    chunk_size: int
    chunk_overlap: int
    chunk_count: int
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    documents: list[DocumentResponse]
    total: int


class ReindexResponse(BaseModel):
    scanned: int
    rebuilt: int
    skipped: int
    removed: int


class RagQueryRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    query: str = Field(min_length=1, max_length=1_000)
    candidate_id: str | None = None
    job_id: str | None = None
    top_k: int | None = Field(default=None, ge=1, le=20)


class SourceReference(BaseModel):
    document_id: str
    chunk_id: str
    chunk_index: int
    score: float
    source_type: str
    filename: str


class RagQueryResponse(BaseModel):
    query: str
    has_evidence: bool
    answer: str
    sources: list[SourceReference]


class JobAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    company: str | None = None
    required_skills: list[str] = Field(default_factory=list, max_length=50)
    preferred_skills: list[str] = Field(default_factory=list, max_length=50)
    experience_required: str | None = Field(default=None, max_length=200)
    education_required: str | None = Field(default=None, max_length=300)
    summary: str = Field(default="", max_length=2_000)
    missing_information: list[str] = Field(default_factory=list, max_length=20)


class JobAnalysisResponse(BaseModel):
    job_id: str
    analysis: JobAnalysis


class CandidateProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str | None = Field(default=None, max_length=200)
    email: str | None = Field(default=None, max_length=254)
    phone: str | None = Field(default=None, max_length=30)
    skills: list[str] = Field(default_factory=list, max_length=60)
    experience_summary: str | None = Field(default=None, max_length=2_000)
    experience: list[dict] = Field(default_factory=list, max_length=20)
    education: str | None = Field(default=None, max_length=500)
    certifications: list[str] = Field(default_factory=list, max_length=30)
    evidence: list[str] = Field(default_factory=list, max_length=20)


class EvidenceItem(BaseModel):
    quote: str = Field(max_length=500)
    source: str = Field(max_length=200)


class MatchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matched_skills: list[str] = Field(default_factory=list, max_length=60)
    missing_skills: list[str] = Field(default_factory=list, max_length=60)
    unverified_skills: list[str] = Field(default_factory=list, max_length=60)
    relevance: Literal["strong", "moderate", "weak"]
    relevance_score: float = Field(ge=0, le=1)
    match_score: float | None = Field(default=None, ge=0, le=100)
    partial_skills: list[str] = Field(default_factory=list, max_length=60)
    experience_comparison: str = Field(default="", max_length=1_000)
    explanation: str = Field(min_length=1, max_length=2_000)
    evidence: list[EvidenceItem] = Field(default_factory=list, max_length=20)


class OllamaMatchResult(MatchResult):
    """Strict local-model contract; API responses retain MatchResult compatibility."""

    match_score: float = Field(ge=0, le=100)
    partial_skills: list[str] = Field(max_length=60)
    experience_comparison: str = Field(min_length=1, max_length=1_000)


class MatchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    job_id: str = Field(min_length=1, max_length=64)
    force_refresh: bool = False


class MatchResponse(BaseModel):
    candidate_id: str
    job_id: str
    match: MatchResult
    cache_status: Literal["hit", "miss", "refresh"] | None = None
    cached: bool = False


class CommunicationDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_type: str
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8_000)
    requires_approval: bool = True


class CommunicationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    draft_type: DraftType
    job_id: str | None = None
    candidate_id: str | None = None
    custom_notes: str | None = Field(default=None, max_length=2_000)


class CommunicationResponse(BaseModel):
    candidate_id: str | None
    job_id: str | None
    draft: CommunicationDraft


class SchedulingSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str = Field(min_length=10, max_length=10)
    time: str = Field(min_length=3, max_length=20)
    status: Literal["suggested", "conflict"]
    reason: str = Field(default="", max_length=300)


class SchedulePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestions: list[SchedulingSuggestion] = Field(
        default_factory=list, max_length=20
    )
    conflicts: list[str] = Field(default_factory=list, max_length=20)


class ScheduleRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    job_id: str | None = None
    candidate_id: str | None = None
    date_start: str = Field(min_length=10, max_length=10)
    date_end: str = Field(min_length=10, max_length=10)
    busy_slots: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("date_start", "date_end")
    @classmethod
    def validate_date(cls, value: str) -> str:
        year, month, day = value.split("-")
        if not (year.isdigit() and month.isdigit() and day.isdigit()):
            raise ValueError("Dates must use the YYYY-MM-DD format.")
        if not (1 <= int(month) <= 12 and 1 <= int(day) <= 31):
            raise ValueError("Dates must use the YYYY-MM-DD format.")
        return value

    @field_validator("date_end")
    @classmethod
    def validate_range(cls, value: str, info):
        start = info.data.get("date_start")
        if start and value < start:
            raise ValueError("date_end must not be before date_start.")
        return value


class ScheduleResponse(BaseModel):
    plan: SchedulePlan


class SupportAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=4_000)
    references: list[SourceReference] = Field(default_factory=list, max_length=20)
