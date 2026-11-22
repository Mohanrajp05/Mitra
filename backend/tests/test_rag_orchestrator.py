import asyncio

import pytest

from app.rag.orchestrator import (
    AGENT_NAMES,
    AgentResult,
    Orchestrator,
    plan_agents,
    reset_orchestrator,
    set_orchestrator,
)


def run(coro):
    return asyncio.run(coro)


class FakeAgent:
    def __init__(self, name, output=None, error=None, delay=0.0):
        self.name = name
        self.output = output
        self.error = error
        self.delay = delay
        self.calls = []

    async def run(self, context):
        self.calls.append(dict(context))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.output


def test_plan_agents_rejects_string():
    with pytest.raises(ValueError):
        plan_agents("job_analysis")


def test_plan_agents_rejects_empty():
    with pytest.raises(ValueError):
        plan_agents([])


def test_plan_agents_rejects_unknown():
    with pytest.raises(ValueError) as excinfo:
        plan_agents(["job_analysis", "not_an_agent"])

    assert "not_an_agent" in str(excinfo.value)


def test_plan_agents_deduplicates():
    assert plan_agents(["communication", "communication"]) == ["communication"]


def test_agent_names_catalog():
    assert set(AGENT_NAMES) == {
        "job_analysis",
        "resume_parsing",
        "communication",
        "interview_scheduling",
        "recruiter_support",
    }


def make_orchestrator(**agents):
    all_agents = {name: FakeAgent(name) for name in AGENT_NAMES}
    all_agents.update(agents)
    return Orchestrator(agents=all_agents)


def test_run_single_agent():
    agent = FakeAgent("communication", output="draft")
    orchestrator = make_orchestrator(communication=agent)

    results = run(orchestrator.run(["communication"], {"job_text": "x"}))

    assert len(results) == 1
    assert results[0].agent == "communication"
    assert results[0].status == "ok"
    assert results[0].output == "draft"
    assert results[0].is_ok
    assert agent.calls == [{"job_text": "x"}]


def test_run_parallel_agents_share_context():
    communication = FakeAgent("communication", output="draft")
    scheduling = FakeAgent("interview_scheduling", output="plan")
    orchestrator = make_orchestrator(
        communication=communication, interview_scheduling=scheduling
    )

    results = run(
        orchestrator.run(
            ["communication", "interview_scheduling"], {"date_start": "d"}
        )
    )

    assert [result.agent for result in results] == [
        "communication",
        "interview_scheduling",
    ]
    assert communication.calls == [{"date_start": "d"}]
    assert scheduling.calls == [{"date_start": "d"}]


def test_run_isolates_agent_errors():
    broken = FakeAgent("communication", error=RuntimeError("boom"))
    healthy = FakeAgent("interview_scheduling", output="plan")
    orchestrator = make_orchestrator(
        communication=broken, interview_scheduling=healthy
    )

    results = run(orchestrator.run(["communication", "interview_scheduling"]))

    statuses = {result.agent: result.status for result in results}
    assert statuses == {
        "communication": "error",
        "interview_scheduling": "ok",
    }
    failed = [result for result in results if result.agent == "communication"][0]
    assert "RuntimeError: boom" in failed.error
    assert not failed.is_ok


def test_agent_result_as_dict():
    result = AgentResult(agent="communication", status="error", error="bad")

    data = result.as_dict()

    assert data == {
        "agent": "communication",
        "status": "error",
        "error": "bad",
        "output": None,
    }


def test_context_isolated_per_request():
    analysis_agent = FakeAgent("job_analysis", output="analysis")
    orchestrator = make_orchestrator(job_analysis=analysis_agent)

    run(orchestrator.run(["job_analysis"], {"job_text": "first"}))
    run(orchestrator.run(["job_analysis"], {"job_text": "second"}))

    assert analysis_agent.calls[0].get("job_text") == "first"
    assert analysis_agent.calls[1].get("job_text") == "second"
    assert "job_analysis" not in analysis_agent.calls[1]


def test_orchestrator_singleton():
    from app.rag.orchestrator import get_orchestrator

    reset_orchestrator()
    first = get_orchestrator()
    second = get_orchestrator()

    assert first is second

    set_orchestrator(Orchestrator(agents={}))
    assert get_orchestrator() is not first

    reset_orchestrator()
