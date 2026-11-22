"""Tests for the deterministic post-check on candidate matching output."""

from app.rag.agents.matching_postcheck import (
    apply_match_postcheck,
    finalize_match,
    quote_in_text,
    skill_in_text,
    normalize_text,
)
from app.schemas.rag import EvidenceItem, MatchResult


def make_match(**overrides) -> MatchResult:
    payload = {
        "matched_skills": ["Python"],
        "missing_skills": [],
        "unverified_skills": [],
        "relevance": "strong",
        "relevance_score": 0.9,
        "explanation": "The profile covers the required skills.",
        "evidence": [EvidenceItem(quote="Python developer", source="resume.txt")],
    }
    payload.update(overrides)
    return MatchResult(**payload)


class TestSkillVerification:
    def test_skill_not_in_resume_is_demoted_to_unverified(self):
        match = make_match(matched_skills=["Python", "Kubernetes"])

        checked, audit = apply_match_postcheck(
            match, "Jane Doe is a Python developer.", ["Python", "Kubernetes"]
        )

        assert checked.matched_skills == ["Python"]
        assert checked.unverified_skills == ["Kubernetes"]
        assert audit["dropped_skills"] == ["Kubernetes"]

    def test_demoted_skill_is_not_reported_missing(self):
        match = make_match(matched_skills=["Kubernetes"])

        checked, _ = apply_match_postcheck(
            match, "Jane Doe is a Python developer.", ["Python", "Kubernetes"]
        )

        assert "Kubernetes" not in checked.missing_skills
        assert "Python" in checked.missing_skills

    def test_common_aliases_are_accepted(self):
        match = make_match(matched_skills=["Node.js", "CI/CD"])

        checked, _ = apply_match_postcheck(
            match,
            "Built services with nodejs and set up continuous integration.",
            ["Node.js", "CI/CD"],
        )

        assert checked.matched_skills == ["Node.js", "CI/CD"]

    def test_empty_resume_demotes_every_claim(self):
        match = make_match(matched_skills=["Python", "SQL"], missing_skills=[])

        checked, audit = apply_match_postcheck(match, "", ["Python", "SQL"])

        assert checked.matched_skills == []
        assert sorted(checked.unverified_skills) == ["Python", "SQL"]
        assert checked.missing_skills == []
        assert sorted(audit["dropped_skills"]) == ["Python", "SQL"]

    def test_skill_helper_normalizes_case_and_spacing(self):
        assert skill_in_text("  python ", normalize_text("PYTHON developer"))
        assert not skill_in_text("Python", normalize_text("Java developer"))

    def test_word_boundaries_prevent_substring_false_positives(self):
        resume = normalize_text("Watching birds migrate and keeping ledgers.")
        assert not skill_in_text("RDS", resume)
        assert not skill_in_text("Go", resume)
        assert not skill_in_text("IAM", resume)

    def test_cloud_skill_aliases_are_recognized(self):
        resume = normalize_text(
            "Deployed on Amazon EKS and Azure Kubernetes Service, provisioned "
            "with HashiCorp Terraform, storage on Amazon RDS, and wrote "
            "python3 scripts with Boto. Practiced FinOps via cloud cost "
            "management reviews. Ran python3 and k8s workloads."
        )
        for skill in ("EKS", "AKS", "Terraform", "RDS", "Python", "Boto3",
                      "FinOps", "Kubernetes"):
            assert skill_in_text(skill, resume), skill


class TestEvidenceVerification:
    def test_quote_absent_from_resume_is_dropped(self):
        match = make_match(
            evidence=[
                EvidenceItem(quote="Python developer", source="resume.txt"),
                EvidenceItem(
                    quote="Led a team of ten engineers", source="resume.txt"
                ),
            ]
        )

        checked, audit = apply_match_postcheck(
            match, "Jane Doe is a Python developer.", ["Python"]
        )

        assert [item.quote for item in checked.evidence] == ["Python developer"]
        assert audit["dropped_quotes"] == 1

    def test_quote_with_different_whitespace_is_kept(self):
        resume = "Designed   PostgreSQL schemas\nfor 40 million rows."
        match = make_match(
            evidence=[
                EvidenceItem(
                    quote="Designed PostgreSQL schemas for 40 million rows",
                    source="resume.txt",
                )
            ]
        )

        checked, audit = apply_match_postcheck(match, resume, ["Python"])

        assert len(checked.evidence) == 1
        assert audit["dropped_quotes"] == 0

    def test_very_short_fabricated_quote_is_dropped(self):
        match = make_match(
            evidence=[EvidenceItem(quote="Rust expert", source="resume.txt")]
        )

        checked, _ = apply_match_postcheck(
            match, "Jane Doe is a Python developer.", ["Python"]
        )

        assert checked.evidence == []

    def test_quote_helper_rejects_empty_text(self):
        assert not quote_in_text("", "python developer")


class TestMissingRecomputation:
    def test_missing_skills_are_rebuilt_from_requirements(self):
        match = make_match(
            matched_skills=["Python"], missing_skills=["SQL"], unverified_skills=[]
        )

        checked, _ = apply_match_postcheck(
            match, "Python developer.", ["Python", "SQL", "Tableau"]
        )

        assert checked.matched_skills == ["Python"]
        assert checked.missing_skills == ["SQL", "Tableau"]

    def test_missing_list_has_no_duplicates(self):
        match = make_match(matched_skills=[], missing_skills=["SQL", "SQL"])

        checked, _ = apply_match_postcheck(match, "Excel only.", ["SQL"])

        assert checked.missing_skills == ["SQL"]

    def test_score_and_explanation_are_preserved(self):
        match = make_match(relevance="moderate", relevance_score=0.55)

        checked, _ = apply_match_postcheck(match, "Python developer.", ["Python"])

        assert checked.relevance == "moderate"
        assert checked.relevance_score == 0.55
        assert checked.explanation == match.explanation


def make_match_result(**overrides) -> MatchResult:
    payload = {
        "matched_skills": [],
        "missing_skills": [],
        "unverified_skills": [],
        "relevance": "weak",
        "relevance_score": 0.0,
        "match_score": 0,
        "partial_skills": [],
        "experience_comparison": "candidate has 6 years; job requires 6 years",
        "explanation": "Assessment.",
        "evidence": [],
    }
    payload.update(overrides)
    return MatchResult(**payload)


CLOUD_RESUME = (
    "Smitha Rao - Cloud Engineer\n"
    "Experience: 6 years of hands-on cloud engineering across AWS and Azure.\n"
    "Migrated a payments platform to Kubernetes (EKS and AKS) with Terraform.\n"
    "Infrastructure as code with Terraform, Azure Bicep and CloudFormation.\n"
    "Automated deployments with Ansible, Helm and GitHub Actions.\n"
    "Networking: VPC, Transit Gateway, IAM, KMS and GuardDuty hardening.\n"
    "Databases: Amazon RDS and Aurora; Lambda for automation.\n"
    "Skills: AWS, Azure, Docker, Kubernetes, EKS, AKS, Terraform, Azure Bicep,\n"
    "CloudFormation, Ansible, Helm, GitHub Actions, VPC, IAM, KMS, Lambda,\n"
    "RDS, Aurora, Python, Boto3, Linux, Prometheus, Grafana, FinOps\n"
)


class TestSkillPromotion:
    def test_overlooked_required_skill_is_promoted_with_evidence(self):
        # The model claimed nothing even though the resume contains Python.
        match = make_match_result()

        finalized, audit = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, 6
        )

        assert finalized.matched_skills == ["Python"]
        assert audit["promoted_skills"] == ["Python"]
        assert any("python" in item.quote.lower() for item in finalized.evidence)

    def test_promoted_skill_counts_towards_score(self):
        match = make_match_result()

        finalized, _ = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, 6
        )

        # Full skill coverage (1/1 required) + experience 6/5 capped at 1.
        assert finalized.match_score == 100.0
        assert finalized.relevance == "strong"

    def test_implied_mention_stays_unverified(self):
        match = make_match_result()
        resume = "Familiar with Kubernetes concepts from a course. Python developer."

        finalized, audit = finalize_match(match, resume, ["Python", "Kubernetes"], 5, 6)

        assert finalized.matched_skills == ["Python"]
        assert "Kubernetes" in finalized.unverified_skills
        assert "Kubernetes" in audit["promoted_partial_skills"]
        assert finalized.partial_skills == ["Kubernetes"]

    def test_absent_skill_is_reported_missing(self):
        match = make_match_result()

        finalized, _ = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python", "Tableau"], 5, 6
        )

        assert finalized.matched_skills == ["Python"]
        assert finalized.missing_skills == ["Tableau"]


class TestDeterministicScore:
    def test_model_score_is_replaced_by_computed_score(self):
        match = make_match_result(match_score=99, relevance_score=0.99, relevance="strong")

        finalized, _ = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, 5
        )

        # Full coverage + exact experience: 100 * (0.8 + 0.2) = 100.
        assert finalized.match_score == 100.0
        assert finalized.relevance_score == 1.0

    def test_partial_skills_count_half(self):
        match = make_match_result()

        finalized, _ = finalize_match(
            match, "Familiar with Kubernetes. Python developer.", ["Python", "Kubernetes"], 5, 5
        )

        # skill component (1 + 0.5) / 2 = 0.75 -> 100 * (0.6 + 0.2) = 80.
        assert finalized.match_score == 80.0
        assert finalized.relevance == "strong"

    def test_lower_experience_reduces_score(self):
        match = make_match_result()

        finalized, _ = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, 2
        )

        # 100 * (0.8 * 1 + 0.2 * 0.4) = 88.
        assert finalized.match_score == 88.0

    def test_extra_model_skills_do_not_inflate_score(self):
        resume = "Jane Doe is a Python developer who also knits."
        match = make_match_result(matched_skills=["Knitting"], evidence=[])

        finalized, _ = finalize_match(match, resume, ["Python", "SQL"], 5, 5)

        # Only Python (promoted) counts: (1 + 0) / 2 = 0.5 -> 100 * 0.6 = 60.
        assert finalized.match_score == 60.0
        assert finalized.relevance == "moderate"

    def test_unknown_experience_is_neutral(self):
        match = make_match_result()

        finalized, _ = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, None
        )

        # 100 * (0.8 + 0.2 * 0.5) = 90.
        assert finalized.match_score == 90.0


class TestEvidenceIntegrity:
    def test_promoted_skills_carry_real_resume_quotes(self):
        match = make_match_result()

        finalized, _ = finalize_match(match, CLOUD_RESUME, ["Terraform", "Datadog"], 6, 6)

        assert "Terraform" in finalized.matched_skills
        assert "Datadog" in finalized.missing_skills
        terraform_quotes = [
            item.quote for item in finalized.evidence if "terraform" in item.quote.lower()
        ]
        assert terraform_quotes
        for quote in terraform_quotes:
            assert quote in normalize_text(CLOUD_RESUME)

    def test_fabricated_model_quotes_are_still_dropped(self):
        match = make_match_result(
            matched_skills=["Python"],
            evidence=[EvidenceItem(quote="Architected a global CDN platform", source="resume.txt")],
        )

        finalized, audit = finalize_match(
            match, "Jane Doe is a Python developer.", ["Python"], 5, 5
        )

        assert finalized.evidence == []
        assert audit["dropped_quotes"] == 1


class TestWeakContextDemotion:
    """Model-claimed matches must meet the same standard as promoted ones."""

    def make_claim(self, skills, evidence_quote=None):
        evidence = []
        if evidence_quote:
            evidence = [EvidenceItem(quote=evidence_quote, source="resume.txt")]
        return make_match(
            matched_skills=skills,
            evidence=evidence,
            missing_skills=[],
            unverified_skills=[],
        )

    def test_familiarity_claim_is_demoted_to_unverified(self):
        # Real eval failure: a resume that only says "Familiar with
        # Kubernetes concepts from a course" was accepted as a match when
        # the model claimed it.
        resume = "Jane audits data. Familiar with Kubernetes concepts from a course."
        match = self.make_claim(["Kubernetes"])

        checked, audit = apply_match_postcheck(match, resume, ["Kubernetes"])

        assert checked.matched_skills == []
        assert checked.unverified_skills == ["Kubernetes"]
        assert audit["dropped_skills"] == []
        assert audit["demoted_skills"] == ["Kubernetes"]

    def test_negated_claim_is_demoted_to_unverified(self):
        resume = "No experience with Tableau; visualizes findings in Excel charts."
        match = self.make_claim(["Tableau"])

        checked, audit = apply_match_postcheck(match, resume, ["Tableau"])

        assert checked.matched_skills == []
        assert checked.unverified_skills == ["Tableau"]
        assert audit["demoted_skills"] == ["Tableau"]

    def test_demonstrated_claim_is_kept(self):
        resume = "Migrated a payments platform to Kubernetes with Terraform."
        match = self.make_claim(["Kubernetes", "Terraform"])

        checked, audit = apply_match_postcheck(match, resume, ["Kubernetes", "Terraform"])

        assert checked.matched_skills == ["Kubernetes", "Terraform"]
        assert audit["demoted_skills"] == []

    def test_course_project_mention_is_demoted(self):
        # Same sentence contains the course cue, so the later "in Flutter"
        # mention is coursework, not professional experience.
        resume = "Completed a Flutter/Dart course and rebuilt a personal expense tracker in Flutter."
        match = self.make_claim(["Flutter"])

        checked, _ = apply_match_postcheck(match, resume, ["Flutter"])

        assert checked.matched_skills == []
        assert checked.unverified_skills == ["Flutter"]

    def test_demoted_claim_scores_as_partial(self):
        # finalize must score the demoted skill as partial (0.5 credit),
        # not full coverage.
        resume = "Jane audits data. Familiar with Kubernetes concepts from a course. Python developer."
        match = self.make_claim(["Python", "Kubernetes"])

        finalized, audit = finalize_match(match, resume, ["Python", "Kubernetes"], 5, 5)

        assert finalized.matched_skills == ["Python"]
        assert finalized.unverified_skills == ["Kubernetes"]
        assert audit["demoted_skills"] == ["Kubernetes"]
        # (1 + 0.5*1)/2 = 0.75 -> 100 * (0.8*0.75 + 0.2*1) = 80.
        assert finalized.match_score == 80.0

    def test_other_occurrence_still_counts_when_strong(self):
        # One weak mention does not sink a skill that is demonstrated
        # elsewhere in the resume.
        resume = (
            "No experience with Tableau at work. "
            "Built executive dashboards in Tableau for three years."
        )
        match = self.make_claim(["Tableau"])

        checked, _ = apply_match_postcheck(match, resume, ["Tableau"])

        assert checked.matched_skills == ["Tableau"]

    def test_not_only_negation_is_not_a_negation(self):
        resume = "Worked not only with Python but also with Go in production."
        match = self.make_claim(["Python"])

        checked, _ = apply_match_postcheck(match, resume, ["Python"])

        assert checked.matched_skills == ["Python"]
