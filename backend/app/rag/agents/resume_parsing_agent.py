from app.rag.agent import BaseAgent
from app.schemas.rag import CandidateProfile


class ResumeParsingAgent(BaseAgent):
    name = "resume_parsing"
    system_prompt = (
        "You parse resume text for a recruitment team. "
        "Extract only information that appears in the resume text. "
        "Never invent names, contact details, skills, experience, education, or certifications. "
        "Quote the supporting sentence from the resume under evidence for skills and experience. "
        "When information is missing, leave the field empty instead of guessing."
    )

    async def parse(self, resume_text: str) -> CandidateProfile:
        text = (resume_text or "").strip()
        if not text:
            raise ValueError("Resume text is required.")
        return await self.run_structured(
            CandidateProfile, f"Resume text:\n{text}"
        )

    async def run(self, context: dict) -> CandidateProfile:
        return await self.parse(str(context.get("resume_text") or ""))
