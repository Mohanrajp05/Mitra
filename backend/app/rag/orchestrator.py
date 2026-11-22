import asyncio
from dataclasses import dataclass
from typing import Any, Sequence

from app.rag.agents.communication_agent import CommunicationAgent
from app.rag.agents.interview_scheduling_agent import InterviewSchedulingAgent
from app.rag.agents.job_analysis_agent import JobAnalysisAgent
from app.rag.agents.recruiter_support_agent import RecruiterSupportAgent
from app.rag.agents.resume_parsing_agent import ResumeParsingAgent
from app.rag.llm import LLMClient, get_llm_client


AGENT_NAMES = (
    "job_analysis",
    "resume_parsing",
    "communication",
    "interview_scheduling",
    "recruiter_support",
)

@dataclass(frozen=True)
class AgentResult:
    agent: str
    status: str
    output: Any = None
    error: str | None = None

    @property
    def is_ok(self) -> bool:
        return self.status == "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "status": self.status,
            "error": self.error,
            "output": (
                self.output.model_dump(mode="json") if hasattr(self.output, "model_dump") else self.output
            ),
        }


def default_agents(llm_client: LLMClient | None = None) -> dict[str, Any]:
    return {
        "job_analysis": JobAnalysisAgent(llm_client),
        "resume_parsing": ResumeParsingAgent(llm_client),
        "communication": CommunicationAgent(llm_client),
        "interview_scheduling": InterviewSchedulingAgent(llm_client),
        "recruiter_support": RecruiterSupportAgent(),
    }


def plan_agents(requested: Sequence[str]) -> list[str]:
    if isinstance(requested, str):
        raise ValueError("requested must be a sequence of agent names, not a string.")

    names = [str(name).strip() for name in requested]
    unknown = [name for name in names if name not in AGENT_NAMES]
    if unknown:
        raise ValueError(f"Unknown agent(s): {', '.join(sorted(set(unknown)))}.")
    if not names:
        raise ValueError("At least one agent must be requested.")

    return list(dict.fromkeys(names))


class Orchestrator:
    def __init__(
        self,
        llm_client: LLMClient | None = None,
        agents: dict[str, Any] | None = None,
    ) -> None:
        self._llm_client = llm_client
        self._agents = agents or default_agents(llm_client)

    async def run(
        self, requested: Sequence[str], context: dict[str, Any] | None = None
    ) -> list[AgentResult]:
        plan = plan_agents(requested)
        context = dict(context or {})

        return list(await asyncio.gather(*(self._run_one(name, context) for name in plan)))

    async def _run_one(
        self, agent_name: str, context: dict[str, Any]
    ) -> AgentResult:
        try:
            output = await self._dispatch(agent_name, context)
            return AgentResult(agent=agent_name, status="ok", output=output)
        except Exception as exc:
            return AgentResult(
                agent=agent_name,
                status="error",
                error=f"{type(exc).__name__}: {exc}",
            )

    async def _dispatch(
        self, agent_name: str, context: dict[str, Any]
    ) -> Any:
        agent = self._agents[agent_name]
        return await agent.run(context)


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator

    if _orchestrator is None:
        _orchestrator = Orchestrator()

    return _orchestrator


def set_orchestrator(orchestrator: Orchestrator | None) -> None:
    global _orchestrator
    _orchestrator = orchestrator


def reset_orchestrator() -> None:
    set_orchestrator(None)
