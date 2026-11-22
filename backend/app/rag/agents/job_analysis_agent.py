from app.rag.agent import BaseAgent
from app.schemas.rag import JobAnalysis


class JobAnalysisAgent(BaseAgent):
    name = "job_analysis"
    system_prompt = (
        "You analyse job descriptions for a recruitment team. "
        "Extract only requirements that are explicitly stated in the text. "
        "Never invent skills, experience levels, or education requirements. "
        "When information is missing, list it under missing_information instead of guessing. "
        "Ignore protected personal characteristics."
    )

    async def analyze(self, job_text: str) -> JobAnalysis:
        text = (job_text or "").strip()
        if not text:
            raise ValueError("Job description text is required.")
        return await self.run_structured(
            JobAnalysis, f"Job description:\n{text}"
        )

    async def run(self, context: dict) -> JobAnalysis:
        return await self.analyze(str(context.get("job_text") or ""))
