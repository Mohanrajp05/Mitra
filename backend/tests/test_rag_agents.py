import asyncio

import pytest

from app.rag.agents.communication_agent import CommunicationAgent
from app.rag.agents.interview_scheduling_agent import InterviewSchedulingAgent
from app.rag.agents.job_analysis_agent import JobAnalysisAgent
from app.rag.agents.recruiter_support_agent import RecruiterSupportAgent
from app.rag.agents.resume_parsing_agent import ResumeParsingAgent
from app.rag.llm import LLMError
from app.rag.pipeline import PipelineResult
from app.schemas.rag import (
    CandidateProfile,
    CommunicationDraft,
    JobAnalysis,
    SchedulePlan,
)


def run(coro):
    return asyncio.run(coro)


class FakeLLMClient:
    def __init__(self, payloads=None, error=None):
        self.payloads = payloads or {}
        self.error = error
        self.calls = []

    async def complete_structured(
        self, model_cls, system_prompt, user_prompt, **kwargs
    ):
        self.calls.append((model_cls.__name__, system_prompt, user_prompt))
        if self.error:
            raise self.error
        payload = self.payloads.get(model_cls.__name__)
        if payload is None:
            raise LLMError(f"no payload configured for {model_cls.__name__}")
        return model_cls.model_validate(payload)


OWNER_ID = "11111111-1111-4111-8111-111111111111"

JOB_ANALYSIS = JobAnalysis(
    title="Backend Engineer",
    required_skills=["Python", "FastAPI"],
    preferred_skills=["Docker"],
    experience_required="3 years",
    summary="Builds APIs.",
)

CANDIDATE_PROFILE = CandidateProfile(
    full_name="Jane Doe",
    skills=["Python", "FastAPI"],
    experience_summary="Five years of backend work.",
    evidence=["Python developer with five years of experience."],
)

DRAFT = CommunicationDraft(
    draft_type="interview_invitation",
    subject="Interview invitation",
    body="Would you like to interview next week?",
)

PLAN = SchedulePlan(
    suggestions=[
        {"date": "2026-11-16", "time": "09:00-10:00", "status": "suggested"},
        {
            "date": "2026-11-16",
            "time": "11:00-12:00",
            "status": "conflict",
            "reason": "busy",
        },
    ],
    conflicts=["2026-11-16 11:00-12:00 is busy."],
)

AGENT_PAYLOADS = {
    "JobAnalysis": JOB_ANALYSIS.model_dump(),
    "CandidateProfile": CANDIDATE_PROFILE.model_dump(),
    "CommunicationDraft": DRAFT.model_dump(),
    "SchedulePlan": PLAN.model_dump(),
}


def test_job_analysis_agent_extracts_structure():
    client = FakeLLMClient(AGENT_PAYLOADS)

    analysis = run(JobAnalysisAgent(client).analyze("Backend Engineer with Python."))

    assert analysis.title == "Backend Engineer"
    assert analysis.required_skills == ["Python", "FastAPI"]
    assert client.calls[0][0] == "JobAnalysis"
    assert client.calls[0][1].startswith("You analyse job descriptions")
    assert client.calls[0][2].startswith("Job description:")


def test_job_analysis_agent_requires_text():
    with pytest.raises(ValueError):
        run(JobAnalysisAgent(FakeLLMClient()).analyze("   "))


def test_resume_parsing_agent_parses_profile():
    client = FakeLLMClient(AGENT_PAYLOADS)

    profile = run(ResumeParsingAgent(client).parse("Jane Doe, Python."))

    assert profile.full_name == "Jane Doe"
    assert "Resume text:" in client.calls[0][2]


def test_resume_parsing_agent_requires_text():
    with pytest.raises(ValueError):
        run(ResumeParsingAgent(FakeLLMClient()).parse("  "))


def test_communication_agent_validates_draft_type():
    with pytest.raises(ValueError):
        run(CommunicationAgent(FakeLLMClient()).draft("newsletter"))


def test_communication_agent_drafts():
    client = FakeLLMClient(AGENT_PAYLOADS)

    draft = run(
        CommunicationAgent(client).draft("follow_up", job_text="Backend role")
    )

    assert draft.subject == "Interview invitation"
    assert draft.requires_approval is True
    assert "Message type: follow_up" in client.calls[0][2]


def test_interview_scheduling_agent_validates_dates():
    agent = InterviewSchedulingAgent(FakeLLMClient())

    with pytest.raises(ValueError):
        run(agent.suggest("", "2026-11-16"))
    with pytest.raises(ValueError):
        run(agent.suggest("2026-11-20", "2026-11-16"))


def test_interview_scheduling_agent_suggests():
    client = FakeLLMClient(AGENT_PAYLOADS)

    plan = run(
        InterviewSchedulingAgent(client).suggest(
            "2026-11-16",
            "2026-11-18",
            busy_slots=["2026-11-16 11:00-12:00"],
        )
    )

    assert len(plan.suggestions) == 2
    assert plan.suggestions[1].status == "conflict"
    assert plan.conflicts
    assert "Availability window: 2026-11-16 to 2026-11-18" in client.calls[0][2]


def test_recruiter_support_agent_requires_owner_and_query():
    agent = RecruiterSupportAgent()

    with pytest.raises(ValueError):
        run(agent.run({"owner_user_id": "", "query": "hello"}))
    with pytest.raises(ValueError):
        run(agent.run({"owner_user_id": OWNER_ID, "query": "   "}))


class FakePipeline:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def run(self, owner_user_id, query, **kwargs):
        self.calls.append((owner_user_id, query, kwargs))
        return self.result


def test_recruiter_support_agent_answers_with_references():
    result = PipelineResult(
        query="Who knows Python?",
        answer="Answer from documents.",
        has_evidence=True,
        sources=[
            {
                "document_id": "doc-1",
                "chunk_id": "chunk-1",
                "chunk_index": 0,
                "score": 0.5,
                "source_type": "resume",
                "filename": "resume.txt",
            }
        ],
    )
    pipeline = FakePipeline(result)

    answer = run(
        RecruiterSupportAgent(pipeline=pipeline).run(
            {"owner_user_id": OWNER_ID, "query": "Who knows Python?"}
        )
    )

    assert answer.answer == "Answer from documents."
    assert answer.references[0].filename == "resume.txt"
    assert pipeline.calls[0][0] == OWNER_ID
    assert pipeline.calls[0][1] == "Who knows Python?"


def test_recruiter_support_agent_forwards_filters():
    pipeline = FakePipeline(
        PipelineResult(query="q", answer="a", has_evidence=False, sources=[])
    )

    run(
        RecruiterSupportAgent(pipeline=pipeline).run(
            {
                "owner_user_id": OWNER_ID,
                "query": "q",
                "candidate_id": "c-1",
                "job_id": "j-1",
                "top_k": 3,
            }
        )
    )

    assert pipeline.calls[0][2] == {
        "candidate_id": "c-1",
        "job_id": "j-1",
        "top_k": 3,
    }


def test_recruiter_support_agent_greets_without_retrieval():
    pipeline = FakePipeline(
        PipelineResult(query="Hi", answer="should not run", has_evidence=False, sources=[])
    )

    answer = run(
        RecruiterSupportAgent(pipeline=pipeline).run(
            {"owner_user_id": OWNER_ID, "query": "Hello!"}
        )
    )

    assert "recruiter AI assistant" in answer.answer
    assert answer.references == []
    assert pipeline.calls == []


@pytest.mark.parametrize(
    "greeting",
    [
        "Hi",
        "HELLO",
        "hey there",
        "Good morning",
        "Thank you",
        "How are you?",
        "what's up?",
    ],
)
def test_recruiter_support_agent_recognizes_greetings(greeting):
    pipeline = FakePipeline(
        PipelineResult(query=greeting, answer="x", has_evidence=False, sources=[])
    )

    answer = run(
        RecruiterSupportAgent(pipeline=pipeline).run(
            {"owner_user_id": OWNER_ID, "query": greeting}
        )
    )

    assert pipeline.calls == []
    assert answer.answer


@pytest.mark.parametrize(
    "real_question",
    [
        "Who knows Python?",
        "Summarize candidate Jane Doe",
        "hello, who has FastAPI experience?",
    ],
)
def test_recruiter_support_agent_non_greetings_still_retrieve(real_question):
    pipeline = FakePipeline(
        PipelineResult(query=real_question, answer="a", has_evidence=True, sources=[])
    )

    run(
        RecruiterSupportAgent(pipeline=pipeline).run(
            {"owner_user_id": OWNER_ID, "query": real_question}
        )
    )

    assert pipeline.calls[0][1] == real_question


def test_agent_without_llm_payload_fails_cleanly():
    with pytest.raises(LLMError):
        run(JobAnalysisAgent(FakeLLMClient()).analyze("text"))
