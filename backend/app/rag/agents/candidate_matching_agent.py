from app.rag.agent import BaseAgent
from app.schemas.rag import MatchResult, OllamaMatchResult


class CandidateMatchingAgent(BaseAgent):
    """Candidate matching runs exclusively on the local Ollama model.

    There is deliberately no Portkey/cloud path on this agent: every match
    score must come from ``match_locally`` so no gateway tokens are spent.
    The final score is recomputed deterministically in the post-check, so the
    model's own score only serves as a cross-check.
    """

    name = "candidate_matching"
    system_prompt = (
        "You compare a structured job analysis with a parsed candidate profile and "
        "produce an explainable relevance assessment. "
        "Use only the job analysis, the candidate profile, and the supplied resume "
        "text. Never invent skills, employers, dates, or experience. "
        "Evaluate EVERY required skill individually, one by one, before deciding "
        "anything. Search the ENTIRE resume text for each skill: professional "
        "experience bullets, projects, certifications and the technical skills "
        "section all count. Do not overlook technologies that are explicitly "
        "mentioned. "
        "Classification per skill: matched only when the resume demonstrates the "
        "skill explicitly (used in real work or projects); partial when the resume "
        "only shows related or adjacent exposure (a closely related tool, or the "
        "skill implied by a described project) - put these in partial_skills; "
        "missing when the skill appears nowhere in the resume text. "
        "A skill that is only named as planned learning, coursework or familiarity "
        "('familiar with', 'currently learning') goes in unverified_skills, never "
        "in matched_skills. "
        "For every matched or partial skill, provide one evidence item whose quote "
        "is copied verbatim from the resume text and names its source. Never "
        "paraphrase quotes and never cite text that is absent from the resume. "
        "In experience_comparison, state the candidate's years against the "
        "required years based only on the profile and resume. "
        "In explanation, name the required skills that are supported, name the "
        "ones that are absent, and point to the strongest resume evidence, in two "
        "or three sentences. "
        "Never consider age, gender, religion, ethnicity, disability, or other "
        "protected characteristics, and never recommend hiring or rejecting a "
        "candidate. This is a relevance assessment only."
    )

    async def match_locally(
        self, local_client, *, job_text: str, required_skills: list[str],
        required_experience, resume_text: str, candidate_experience,
    ) -> MatchResult:
        """Run the match-only assessment locally, without the Portkey client."""
        numbered_skills = "\n".join(
            f"{index}. {skill}" for index, skill in enumerate(required_skills, 1)
        ) or "(none listed)"
        prompt = (
            "Complete job description:\n"
            f"{job_text}\n\n"
            f"Required experience: {required_experience} years\n\n"
            "Required skills (evaluate each one individually against the resume, "
            "in this exact order, and decide matched / partial / missing for "
            f"each):\n{numbered_skills}\n\n"
            f"Complete candidate resume:\n{resume_text}\n\n"
            f"Candidate experience on profile: {candidate_experience} years\n\n"
            "For every required skill list, scan the full resume (experience, "
            "projects, skills section) for supporting evidence. Return "
            "match_score as an integer from 0 to 100, partial_skills for skills "
            "with only related exposure, unverified_skills for skills mentioned "
            "as planned learning or coursework, missing_skills for absent "
            "skills, and an experience_comparison. Provide one verbatim resume "
            "quote per matched or partial skill. Classify conservatively: when "
            "in doubt, the skill is missing, not matched."
        )
        return await local_client.complete_structured(OllamaMatchResult, self.system_prompt, prompt)
