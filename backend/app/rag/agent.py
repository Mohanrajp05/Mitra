from typing import TypeVar

from pydantic import BaseModel

from app.rag.llm import LLMClient, get_llm_client

ModelT = TypeVar("ModelT", bound=BaseModel)


class AgentError(RuntimeError):
    pass


class BaseAgent:
    name = "agent"
    system_prompt = ""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        self._llm_client = llm_client

    @property
    def client(self) -> LLMClient:
        if self._llm_client is None:
            self._llm_client = get_llm_client()
        return self._llm_client

    async def run_structured(
        self, model_cls: type[ModelT], user_prompt: str
    ) -> ModelT:
        if not self.system_prompt:
            raise AgentError(f"{self.name} has no system prompt configured.")
        return await self.client.complete_structured(
            model_cls, self.system_prompt, user_prompt
        )
