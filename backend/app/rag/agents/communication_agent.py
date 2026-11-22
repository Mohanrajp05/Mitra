from app.rag.agent import BaseAgent
from app.schemas.rag import CommunicationDraft


class CommunicationAgent(BaseAgent):
    name = "communication"
    system_prompt = (
        "You draft professional recruitment messages for a recruiter to review. "
        "Produce a draft only. Never claim that a message was sent. "
        "Use only the job and candidate context provided. "
        "Never invent facts about the candidate or the company. "
        "Keep the tone professional and include next-step instructions for the recruiter."
    )

    async def draft(
        self,
        draft_type: str,
        job_text: str = "",
        candidate_text: str = "",
        custom_notes: str = "",
    ) -> CommunicationDraft:
        if draft_type not in ("interview_invitation", "follow_up", "application_status"):
            raise ValueError(
                "draft_type must be interview_invitation, follow_up, or application_status."
            )

        user_prompt = f"Message type: {draft_type}\n"
        user_prompt += f"Job context:\n{job_text.strip() or 'None provided.'}\n\n"
        user_prompt += f"Candidate context:\n{candidate_text.strip() or 'None provided.'}\n\n"
        user_prompt += f"Recruiter notes:\n{custom_notes.strip() or 'None provided.'}"

        return await self.run_structured(CommunicationDraft, user_prompt)

    async def run(self, context: dict) -> CommunicationDraft:
        return await self.draft(
            str(context.get("draft_type") or ""),
            str(context.get("job_text") or ""),
            str(context.get("candidate_text") or ""),
            str(context.get("custom_notes") or ""),
        )
