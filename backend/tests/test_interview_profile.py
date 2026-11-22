"""Regression tests for interview resume profile extraction."""

from pathlib import Path

from app.rag.interview_profile import extract_profile, split_sections
from app.services import interview_service

RESUME_PDF = Path(
    r"D:\AI-agent-requirement\AI-Recruitment-Agent\backend\data\rag\documents"
    r"\197daf95-9c95-40cb-978d-40bfe5adfd56__Mohan - UI_UX Developer Resume.pdf"
)


def _actual_resume_text() -> str:
    from app.rag.document_loader import load_document

    loaded = load_document(
        filename=RESUME_PDF.name,
        data=RESUME_PDF.read_bytes(),
        max_bytes=20 * 1024 * 1024,
        max_chars=200000,
        content_type="application/pdf",
    )
    return loaded.text


def test_real_resume_identity_fields():
    profile = extract_profile(_actual_resume_text())
    assert profile["candidate_name"] == "Mohan"
    assert profile["job_title"] == "UI/UX Developer & Frontend Product Designer"
    assert profile["location"] == "Bengaluru, India"
    assert profile["email"] == "mohan.uiux@email.com"
    assert profile["phone"] == "+91 98453 56789"


def test_real_resume_summary_and_experience_duration():
    profile = extract_profile(_actual_resume_text())
    assert "4+ years" in profile["professional_summary"]
    assert profile["total_experience"] == "4+ years"
    assert "Figma" in profile["professional_summary"]


def test_real_resume_technical_and_design_skills():
    profile = extract_profile(_actual_resume_text())
    joined_technical = " ".join(profile["technical_skills"])
    joined_design = " ".join(profile["design_skills"])
    for skill in ("React.js", "TypeScript", "HTML5", "CSS3", "Tailwind CSS"):
        assert skill in joined_technical
    for skill in ("Figma", "Adobe XD", "Wireframing", "Interactive Prototyping", "WCAG"):
        assert skill in joined_design


def test_real_resume_multiple_work_experiences():
    profile = extract_profile(_actual_resume_text())
    experience = profile["work_experience"]
    assert len(experience) == 2
    assert experience[0]["title"] == "UI/UX Developer"
    assert "PixelCraft" in experience[0]["company"]
    assert experience[0]["period"] == "August 2023 – Present"
    assert experience[1]["title"] == "Associate UI/UX Designer & Frontend Developer"
    assert "BrightWave" in experience[1]["company"]
    assert experience[1]["period"] == "July 2021 – July 2023"
    assert all(entry.get("responsibilities") for entry in experience)


def test_real_resume_multiple_projects_with_technologies():
    profile = extract_profile(_actual_resume_text())
    projects = profile["projects"]
    assert len(projects) == 2
    assert projects[0]["title"] == "Enterprise SaaS Design System & Component Library"
    assert "Storybook" in projects[0]["technologies"]
    assert projects[1]["title"] == "FinTech Mobile Banking UX Redesign & Prototype"
    assert "Figma" in projects[1]["technologies"]
    assert all(project.get("description") for project in projects)


def test_real_resume_education_and_certifications():
    profile = extract_profile(_actual_resume_text())
    assert len(profile["education"]) == 1
    assert "B.Des" in profile["education"][0]
    assert "BMS Institute of Technology" in profile["education"][0]
    assert "2017" in profile["education"][0] and "2021" in profile["education"][0]
    certifications = " ".join(profile["certifications"])
    assert "Google UX Design Professional Certificate" in certifications
    assert "Meta Front-End Developer Certificate" in certifications
    assert "W3C Web Accessibility" in certifications


def test_real_resume_sections_are_not_mixed():
    profile = extract_profile(_actual_resume_text())
    experience_titles = " ".join(str(e.get("title") or "") for e in profile["work_experience"])
    assert "Design System" not in experience_titles  # project, not a job
    assert "FinTech" not in experience_titles  # project, not a job
    assert "B.Des" not in experience_titles  # education, not a job
    certification_text = " ".join(profile["certifications"])
    assert "BMS Institute" not in certification_text


def test_wrapped_text_and_section_detection():
    text = (
        "Jane Doe\nFrontend Engineer\nBerlin, Germany | jane@example.com | +49 151 12345678\n"
        "PROFESSIONAL SUMMARY\nPassionate frontend engineer with 3+ years of experience.\n"
        "TECHNICAL & DESIGN SKILLS\nUI/UX Design &\nPrototyping:\nFigma, Wireframing\n"
        "Frontend Development: React, TypeScript\n"
        "WORK EXPERIENCE\nFrontend Engineer — Acme Corp Berlin | January 2022 – Present\n"
        "Built accessible interfaces and\nreduced load time by 30%.\n"
        "KEY UI/UX PROJECTS\nDesign System | Figma, React\nCreated shared components.\n"
        "EDUCATION & CERTIFICATIONS\nB.Sc in Computer Science — Example University, 2018 - 2021\n"
        "Google UX Certificate\n"
    )
    sections = split_sections(text)
    assert set(sections) >= {"summary", "skills", "experience", "projects", "education"}
    profile = extract_profile(text)
    assert profile["candidate_name"] == "Jane Doe"
    assert profile["job_title"] == "Frontend Engineer"
    assert len(profile["work_experience"]) == 1
    assert len(profile["projects"]) == 1
    assert "Reduced load time" not in " ".join(profile["work_experience"][0]["responsibilities"])
    assert "reduced load time by 30%" in " ".join(profile["work_experience"][0]["responsibilities"])
    assert profile["work_experience"][0]["period"] == "January 2022 – Present"


def test_missing_fields_remain_empty():
    profile = extract_profile("Just a short unstructured sentence.")
    assert profile["candidate_name"] is None
    assert profile["technical_skills"] == []
    assert profile["work_experience"] == []
    assert profile["projects"] == []
    assert profile["certifications"] == []


def test_empty_or_unreadable_documents():
    for text in ("", None, "   \n  "):
        profile = extract_profile(text)
        assert profile["candidate_name"] is None
        assert profile["work_experience"] == []
        assert profile["technical_skills"] == []


def test_interview_service_uses_corrected_profile():
    profile = interview_service.extract_interview_info(_actual_resume_text())
    assert profile["candidate_name"] == "Mohan"
    assert len(profile["work_experience"]) == 2
    assert len(profile["projects"]) == 2
    assert profile["design_skills"]


def test_document_text_uses_original_file_not_chunks(monkeypatch):
    class FakeStore:
        def open_original(self, owner_user_id, document_id):
            return (RESUME_PDF, "application/pdf", RESUME_PDF.name)

    monkeypatch.setattr(interview_service, "get_document_store", lambda: FakeStore())
    text = interview_service._document_text("user-id", "document-id")
    assert "Wireframing" in text and "Figma" in text
    profile = interview_service.extract_interview_info(text)
    assert len(profile["work_experience"]) == 2
    assert len(profile["projects"]) == 2


def test_interview_context_uses_corrected_profile():
    session = {
        "extracted_info": extract_profile(_actual_resume_text()),
        "resume_filename": "resume.pdf",
        "candidate_role": None,
    }
    context = interview_service._interview_context(session)
    assert context["candidate_name"] == "Mohan"
    assert context["candidate_role"] == "UI/UX Developer & Frontend Product Designer"
    assert "React.js" in " ".join(context["skills"])
    assert "Figma" in " ".join(context["design_skills"])
    assert any("Enterprise SaaS Design System" in project for project in context["projects"])
    assert any("PixelCraft" in entry for entry in context["experience"])
