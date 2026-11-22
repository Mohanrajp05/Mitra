"""Tests for the deterministic resume profile parser.

The parser must never invent anything: every returned string must be a
substring of the input resume text, and sections the resume does not
clearly contain must stay empty.
"""

import pytest

from app.rag import resume_profile

STRUCTURED_RESUME = """Jane Doe
Senior Cloud Engineer
jane.doe@example.com | +91 98765 43210

Summary
Cloud engineer with 8 years of experience across AWS and Azure.

Professional Experience
Senior Cloud Engineer at Acme Corp, 2019 - Present
Cloud Engineer | Globex | 2016 - 2019
Globex, Junior Developer, 2014 - 2016

Education
B.Tech Computer Science, NIT Trichy, 2014

Certifications
AWS Certified Solutions Architect - Associate
"""

UNSTRUCTURED_RESUME = (
    "Jane Doe builds web apps with React and Node.js. "
    "She has 4 years of experience and loves shipping."
)


def assert_no_invention(result: dict, resume: str) -> None:
    normalized = resume_profile.re.sub(r"\s+", " ", resume.lower())
    for skill in result["skills"]:
        assert resume_profile.re.sub(r"\s+", " ", skill.lower()) in normalized, skill
    for entry in result["experience"]:
        for value in entry.values():
            if value:
                assert resume_profile.re.sub(r"\s+", " ", value.lower()) in normalized, value
    for value in result["education"] + result["certifications"]:
        assert resume_profile.re.sub(r"\s+", " ", value.lower()) in normalized, value


def test_structured_resume_extracts_all_sections():
    result = resume_profile.extract_profile_sections(STRUCTURED_RESUME)

    assert result["summary"] == "Cloud engineer with 8 years of experience across AWS and Azure."
    assert result["total_years"] == 8.0
    assert result["email"] == "jane.doe@example.com"
    assert result["phone"] == "+91 98765 43210"
    assert {"title": "Senior Cloud Engineer", "company": "Acme Corp", "period": "2019 - Present"} in result["experience"]
    assert {"title": "Cloud Engineer", "company": "Globex", "period": "2016 - 2019"} in result["experience"]
    assert {"title": "Junior Developer", "company": "Globex", "period": "2014 - 2016"} in result["experience"]
    assert result["education"] == ["B.Tech Computer Science, NIT Trichy, 2014"]
    assert result["certifications"] == ["AWS Certified Solutions Architect - Associate"]
    assert_no_invention(result, STRUCTURED_RESUME)


def test_inline_skill_header_with_wrapped_list_is_parsed():
    resume = (
        "Smitha Rao\nCloud Engineer\nsmitha.rao@example.com\n\n"
        "Experience\n- 6+ years of hands-on cloud engineering across AWS and Azure.\n"
        "- Migrated a payments platform to Kubernetes (EKS and AKS) with Terraform.\n\n"
        "Skills: AWS, Azure, Docker, Kubernetes, EKS, AKS, Terraform, Azure Bicep,\n"
        "CloudFormation, Ansible, Helm, GitHub Actions, VPC, IAM, KMS, Lambda, RDS,\n"
        "Aurora, Python, Boto3, Linux, Prometheus, Grafana, FinOps\n"
    )
    result = resume_profile.extract_profile_sections(resume)

    assert "AWS" in result["skills"]
    assert "Kubernetes" in result["skills"]
    assert "FinOps" in result["skills"]
    assert len(result["skills"]) == 24
    assert result["total_years"] == 6.0
    assert_no_invention(result, resume)


def test_unstructured_resume_stays_sparse():
    result = resume_profile.extract_profile_sections(UNSTRUCTURED_RESUME)

    # Nothing is structured in this text: every section stays empty so the
    # caller can fall back to the local model instead of guessing.
    assert result["skills"] == []
    assert result["experience"] == []
    assert result["summary"] is None


def test_empty_text_returns_empty_profile():
    result = resume_profile.extract_profile_sections("")

    assert result["skills"] == []
    assert result["summary"] is None
    assert result["total_years"] is None


def test_year_ranges_are_not_mistaken_for_phone_numbers():
    resume = (
        "Jane Doe\nCloud Engineer\n2019 - 2023 worked on platforms\n"
        "2014 - 2016 earlier role\n"
    )
    result = resume_profile.extract_profile_sections(resume)

    assert result["phone"] is None


def test_negated_year_statement_is_not_taken_as_experience():
    resume = "Jane Doe\nNo 5 years of experience yet; eager to learn.\n"
    result = resume_profile.extract_profile_sections(resume)

    # "No ... years of experience" must not become total_years=5.
    assert result["total_years"] is None


def test_narrative_experience_lines_do_not_become_fake_entries():
    resume = (
        "Experience\n"
        "- Migrated a payments platform to Kubernetes with Terraform.\n"
        "- Automated deployments with Ansible and Helm.\n"
    )
    result = resume_profile.extract_profile_sections(resume)

    assert result["experience"] == []


def test_ambiguous_comma_entry_is_skipped():
    resume = (
        "Experience\n"
        "Acme Corp, somewhere, 2019 - 2023\n"
    )
    result = resume_profile.extract_profile_sections(resume)

    # Neither segment contains a role word: assigning title/company would be
    # a guess, so the line is skipped entirely.
    assert result["experience"] == []


def test_skills_are_deduplicated_and_capped():
    resume = "Skills: " + ", ".join(f"skill{i}" for i in range(80))
    result = resume_profile.extract_profile_sections(resume)

    assert len(result["skills"]) == resume_profile.MAX_SKILLS
    assert len({skill.lower() for skill in result["skills"]}) == resume_profile.MAX_SKILLS
