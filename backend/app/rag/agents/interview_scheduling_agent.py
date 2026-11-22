from app.rag.agent import BaseAgent
from app.schemas.rag import SchedulePlan


class InterviewSchedulingAgent(BaseAgent):
    name = "interview_scheduling"
    system_prompt = (
        "You suggest interview date and time slots for a recruiter to review. "
        "Use only the recruiter-provided availability window and busy slots. "
        "Never assume calendar availability that was not provided. "
        "Do not book interviews or send invitations. "
        "Mark every slot that overlaps a busy slot with status conflict and explain why. "
        "Suggest at most 5 slots between date_start and date_end."
    )

    async def suggest(
        self,
        date_start: str,
        date_end: str,
        busy_slots: list[str] | None = None,
        job_text: str = "",
        candidate_text: str = "",
    ) -> SchedulePlan:
        start = (date_start or "").strip()
        end = (date_end or "").strip()
        if not start or not end:
            raise ValueError("date_start and date_end are required.")
        if end < start:
            raise ValueError("date_end must not be before date_start.")

        blocked = [slot for slot in (busy_slots or []) if slot and slot.strip()]
        user_prompt = (
            f"Availability window: {start} to {end}\n"
            f"Busy slots (do not schedule):\n"
            + ("\n".join(blocked) if blocked else "None provided.")
            + "\n\nJob context:\n"
            + (job_text.strip() or "None provided.")
            + "\n\nCandidate context:\n"
            + (candidate_text.strip() or "None provided.")
        )

        return await self.run_structured(SchedulePlan, user_prompt)

    async def run(self, context: dict) -> SchedulePlan:
        return await self.suggest(
            str(context.get("date_start") or ""),
            str(context.get("date_end") or ""),
            list(context.get("busy_slots") or []),
            str(context.get("job_text") or ""),
            str(context.get("candidate_text") or ""),
        )
