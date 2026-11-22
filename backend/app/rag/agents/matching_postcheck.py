"""Post-check for candidate matching output.

The matching agent is an LLM and can hallucinate: it may claim a skill is
matched when the resume never mentions it, or attach an "evidence" quote that
does not exist in the resume text. This module applies deterministic
verification on top of the model output:

  - matched skills must appear in the resume text (with common aliases,
    matched on word boundaries); anything else is demoted to unverified_skills
  - evidence quotes must exist in the resume text (normalized whitespace);
    anything else is dropped
  - required skills that ARE demonstrably in the resume but that the model
    failed to claim are promoted to matched with an evidence quote extracted
    from the resume itself (the model may overlook items in long skill lists)
  - mentions that only occur next to cues such as "familiar with" or
    "coursework", or under a negation ("no experience with X"), stay
    unverified instead of being promoted or counted as matched
  - missing_skills is recomputed from the job requirements so the three lists
    stay mutually consistent
  - the final score is recomputed deterministically from the validated skill
    coverage and the required experience, so the model cannot return an
    arbitrary score inconsistent with the evidence (see SCORING WEIGHTS below)

The result is an explainable MatchResult where every remaining claim has text
evidence behind it.

Scoring weights (documented contract):
  score = 100 * (0.8 * skill_coverage + 0.2 * experience_coverage)
  skill_coverage      = (matched_required + 0.5 * partial_required) / required_total
  experience_coverage = min(1, candidate_experience / required_experience),
                        1.0 when the job has no experience requirement, and a
                        neutral 0.5 when the candidate value is unknown.
  relevance: strong >= 75, moderate >= 45, weak below.
"""

import re

from app.schemas.rag import EvidenceItem

SKILL_ALIASES = {
    "node.js": ["nodejs", "node js", "node"],
    "node": ["nodejs", "node.js"],
    "ci/cd": ["ci cd", "ci-cd", "continuous integration", "continuous delivery"],
    "apache spark": ["spark"],
    "api documentation": ["api docs", "documenting apis", "openapi"],
    "developer tools": ["postman", "curl", "dev tools"],
    "usability testing": ["usability tests", "usability sessions", "user testing"],
    "lead generation": ["outbound prospecting", "prospecting"],
    # Cloud and DevOps aliases (canonical -> resume spellings).
    "aws": ["amazon web services", "amazon aws"],
    "azure": ["microsoft azure"],
    "eks": ["amazon eks", "aws eks", "elastic kubernetes service"],
    "aks": ["azure kubernetes service"],
    "rds": ["amazon rds", "aws rds", "relational database service"],
    "aurora": ["amazon aurora", "aws aurora"],
    "lambda": ["aws lambda", "amazon lambda"],
    "iam": ["identity and access management", "aws iam"],
    "kms": ["key management service", "aws kms"],
    "guardduty": ["guard duty", "aws guardduty"],
    "vpc": ["virtual private cloud", "aws vpc"],
    "transit gateway": ["aws transit gateway"],
    "azure bicep": ["bicep", "azure bicep templates"],
    "cloudformation": ["cloud formation", "aws cloudformation"],
    "github actions": ["github action", "github workflows"],
    "azure devops": ["microsoft azure devops"],
    "kubernetes": ["k8s"],
    "python": ["python3"],
    "boto3": ["boto", "boto 3"],
    "finops": ["cloud financial operations", "cloud cost management"],
    "terraform": ["hashicorp terraform"],
    "docker": ["dockerized", "docker engine"],
    "ansible": ["red hat ansible"],
    "helm": ["helm charts", "kubernetes helm"],
    "prometheus": ["prometheus monitoring", "prometheus alerts"],
    "grafana": ["grafana dashboards"],
    "datadog": ["data dog", "datadog monitoring"],
    "linux": ["red hat enterprise linux", "rhel"],
}

# Phrases that mean a skill is mentioned but not yet demonstrated.
# Mirrors the evaluation harness (eval/run_eval.py WEAK_CONTEXT_PATTERN) so the
# app and the evaluation apply the same "not professional experience yet"
# standard: coursework, tutorials, familiarity, watching/reading about a tool,
# or hearsay is never professional evidence.
WEAK_CONTEXT_PATTERN = re.compile(
    r"(?:"
    r"familiar(?:ity)? with|exposure to|aware(?:ness)? of|"
    r"heard (?:of|about)|read (?:of|about|the)|watched|attending|attended|"
    r"(?:completed|followed|took|taking|enrolled in)\s+(?:a|an|one|the)?\s*"
    r"(?:[\w/+-]+\s+){0,4}(?:course|workshop|tutorial|webinar|bootcamp|class|series)|"
    r"course\s?work|tutorial|webinar|bootcamp|"
    r"lists? .{0,50} under|mentions? .{0,60} under|"
    r"explor(?:e|ed|ing)|studied (?:for|the)|currently (?:learning|studying)|"
    r"plann?(?:ed|ing)? to|interested in|"
    r"bookmarks?|knows? (?:what|the term)|"
    r"only for (?:simple|basic)|copied from|pair-programmed|"
    r"selenium ide|recordings?|shadowed|user stories|sat in|demos|"
    r"in every proposal deck|built by (?:the )?client teams|"
    r"interviewed engineers about"
    r")",
    re.IGNORECASE,
)

# A skill occurrence directly preceded by a negation ("no experience with
# X", "never used X") is not demonstrated either. "not only" is excluded so
# "worked not only with Python but also with Go" stays a positive claim.
NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|without|zero|none)\b(?! only)[^.;]{0,50}$",
    re.IGNORECASE,
)

SKILL_WEIGHT = 0.8
EXPERIENCE_WEIGHT = 0.2
PARTIAL_SKILL_CREDIT = 0.5
STRONG_SCORE_THRESHOLD = 75.0
MODERATE_SCORE_THRESHOLD = 45.0


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _skill_pattern(needle: str) -> re.Pattern | None:
    """Compile a word-boundary pattern for a skill and its aliases."""
    variants = sorted({needle, *SKILL_ALIASES.get(needle, [])}, key=len, reverse=True)
    if not variants:
        return None
    parts = []
    for variant in variants:
        tokens = re.split(r"\s+", variant)
        parts.append(r"\s+".join(re.escape(token) for token in tokens))
    return re.compile(r"(?<!\w)(?:" + "|".join(parts) + r")(?!\w)")


def skill_occurrences(skill: str, normalized_resume: str) -> list[re.Match]:
    needle = normalize_text(skill)
    if not needle:
        return []
    pattern = _skill_pattern(needle)
    if pattern is None:
        return []
    return list(pattern.finditer(normalized_resume or ""))


def skill_in_text(skill: str, normalized_resume: str) -> bool:
    return bool(skill_occurrences(skill, normalized_resume))


def _occurrence_context(normalized_resume: str, start: int, end: int, pad: int = 60) -> str:
    """Text around an occurrence, clipped to the surrounding sentence."""
    left = max(0, start - pad)
    right = min(len(normalized_resume), end + pad)
    sentence_start = max(
        normalized_resume.rfind(". ", left, start),
        normalized_resume.rfind("\n", left, start),
    )
    if sentence_start != -1:
        left = sentence_start + 1
    ends = [
        pos
        for pos in (
            normalized_resume.find(". ", end, right),
            normalized_resume.find("\n", end, right),
        )
        if pos != -1
    ]
    if ends:
        right = min(ends) + 1
    return normalized_resume[left:right]


def _skill_before_context(normalized_resume: str, start: int) -> str:
    """Text immediately before a skill occurrence, clipped to its sentence.

    Starts at most 90 characters back (mirroring the evaluation harness)
    but never crosses a sentence boundary (". " or a newline): weak context
    or a negation must belong to the same sentence as the skill mention,
    otherwise a skill following an unrelated weak sentence would be
    wrongly demoted.
    """
    left = max(0, start - 90)
    boundary = max(
        normalized_resume.rfind(". ", left, start),
        normalized_resume.rfind("\n", left, start),
    )
    if boundary != -1:
        left = boundary + 1
    return normalized_resume[left:start]


def _demonstration_window(normalized_resume: str, start: int, end: int) -> str:
    """Text context used to judge a skill occurrence.

    Mirrors the evaluation harness (eval/run_eval.py skill_status): up to 90
    characters before the occurrence plus 40 after, so weak-context cues
    that open the sentence ("Completed a Flutter/Dart course and rebuilt
    ... in Flutter") are still visible to later mentions in the same line.
    """
    before = _skill_before_context(normalized_resume, start)
    return before + " " + normalized_resume[end : end + 40]


def skill_is_demonstrated(skill: str, normalized_resume: str) -> bool:
    """True when at least one occurrence is a professional, non-negated mention.

    An occurrence is NOT demonstrated when it is directly preceded by a
    negation ("no experience with X") or when its surrounding text reads as
    coursework / familiarity / hearsay (WEAK_CONTEXT_PATTERN). Any other
    occurrence counts as demonstrated.
    """
    for match in skill_occurrences(skill, normalized_resume):
        before = _skill_before_context(normalized_resume, match.start())
        if NEGATION_PATTERN.search(before):
            continue
        if WEAK_CONTEXT_PATTERN.search(
            _demonstration_window(normalized_resume, match.start(), match.end())
        ):
            continue
        return True
    return False


def evidence_quote_for_skill(
    skill: str, normalized_resume: str, context_chars: int = 70
) -> str | None:
    """Extract a short quote around a demonstrated skill occurrence."""
    for match in skill_occurrences(skill, normalized_resume):
        start = max(0, match.start() - context_chars)
        end = min(len(normalized_resume), match.end() + context_chars)
        quote = normalized_resume[start:end].strip()
        if start > 0 and " " in quote:
            quote = quote[quote.find(" ") + 1:]
        if end < len(normalized_resume) and " " in quote:
            quote = quote[: quote.rfind(" ")]
        quote = quote.strip()
        if quote:
            return quote
    return None


def quote_in_text(quote: str, normalized_resume: str) -> bool:
    fragment = normalize_text(quote).strip("\"'“”‘’")
    if not fragment:
        return False
    if fragment in normalized_resume:
        return True
    words = fragment.split()
    if len(words) < 4:
        return False
    window = " ".join(words[: max(4, len(words) - 2)])
    return window in normalized_resume


def apply_match_postcheck(match, resume_text: str, required_skills):
    """Verify a MatchResult against the resume text.

    Returns (MatchResult, audit) where audit lists what was dropped so the
    caller can log or report it.

    Model-claimed matches are held to the same standard as promoted ones:
    a claim must be present in the resume text AND demonstrated
    (skill_is_demonstrated). Mentions that only appear in weak context
    ("familiar with", coursework, tutorials) or under a negation are demoted
    to unverified skills instead of counting as matched; audit
    ``demoted_skills`` records them separately from ``dropped_skills``
    (claims that do not appear in the resume at all).
    """
    normalized_resume = normalize_text(resume_text)
    dropped_skills = []
    demoted_skills = []
    dropped_quotes = 0

    verified_matched = []
    unverified = list(match.unverified_skills)
    for skill in match.matched_skills:
        if not skill_in_text(skill, normalized_resume):
            if skill not in unverified:
                unverified.append(skill)
            dropped_skills.append(skill)
        elif not skill_is_demonstrated(skill, normalized_resume):
            if skill not in unverified:
                unverified.append(skill)
            demoted_skills.append(skill)
        elif skill not in verified_matched:
            verified_matched.append(skill)

    verified_quotes = []
    for item in match.evidence:
        if quote_in_text(item.quote, normalized_resume):
            verified_quotes.append(item)
        else:
            dropped_quotes += 1

    claimed = {normalize_text(skill) for skill in verified_matched + unverified}
    missing = []
    for skill in list(required_skills or []) + list(match.missing_skills):
        key = normalize_text(skill)
        if key and key not in claimed and key not in {normalize_text(s) for s in missing}:
            missing.append(skill)

    verified = match.model_copy(
        update={
            "matched_skills": verified_matched,
            "unverified_skills": unverified,
            "missing_skills": missing,
            "evidence": verified_quotes,
        }
    )
    audit = {
        "dropped_skills": dropped_skills,
        "demoted_skills": demoted_skills,
        "dropped_quotes": dropped_quotes,
    }
    return verified, audit


def _unique_by_key(skills) -> list:
    seen = set()
    unique = []
    for skill in skills:
        key = normalize_text(skill)
        if key and key not in seen:
            seen.add(key)
            unique.append(skill)
    return unique


def compute_match_score(
    matched_skills,
    partial_skills,
    required_skills,
    required_experience,
    candidate_experience,
) -> tuple[float, str]:
    """Deterministic score from validated skill coverage and experience."""
    required_keys = {normalize_text(s) for s in _unique_by_key(required_skills or [])}
    if required_keys:
        matched_keys = {normalize_text(s) for s in matched_skills or []} & required_keys
        partial_keys = {normalize_text(s) for s in partial_skills or []} & required_keys
        skill_component = (
            len(matched_keys) + PARTIAL_SKILL_CREDIT * len(partial_keys)
        ) / len(required_keys)
    else:
        skill_component = 1.0

    if required_experience and float(required_experience) > 0:
        if candidate_experience is None:
            experience_component = 0.5
        else:
            experience_component = min(
                1.0,
                max(0.0, float(candidate_experience) / float(required_experience)),
            )
    else:
        experience_component = 1.0

    score = 100.0 * (
        SKILL_WEIGHT * skill_component + EXPERIENCE_WEIGHT * experience_component
    )
    score = round(min(100.0, max(0.0, score)), 1)
    if score >= STRONG_SCORE_THRESHOLD:
        relevance = "strong"
    elif score >= MODERATE_SCORE_THRESHOLD:
        relevance = "moderate"
    else:
        relevance = "weak"
    return score, relevance


def finalize_match(
    match,
    resume_text: str,
    required_skills,
    required_experience,
    candidate_experience,
):
    """Verify, complete and score a match result deterministically.

    Applies apply_match_postcheck, then promotes required skills that are
    demonstrably present in the resume but that the model failed to claim
    (with resume-extracted evidence), and finally recomputes the score from
    the validated lists so the model cannot set an arbitrary score.

    Returns (MatchResult, audit).
    """
    match, audit = apply_match_postcheck(match, resume_text, required_skills)
    normalized_resume = normalize_text(resume_text)

    claimed = {
        normalize_text(skill)
        for skill in match.matched_skills + match.unverified_skills
    }
    promoted_matched = []
    promoted_partial = []
    existing_quotes = {normalize_text(item.quote) for item in match.evidence}
    for skill in _unique_by_key(required_skills or []):
        key = normalize_text(skill)
        if not key or key in claimed:
            continue
        if skill_is_demonstrated(skill, normalized_resume):
            match.matched_skills.append(skill)
            promoted_matched.append(skill)
            quote = evidence_quote_for_skill(skill, normalized_resume)
            if (
                quote
                and normalize_text(quote) not in existing_quotes
                and len(match.evidence) < 20
            ):
                match.evidence.append(EvidenceItem(quote=quote, source="resume"))
                existing_quotes.add(normalize_text(quote))
        elif skill_occurrences(skill, normalized_resume):
            match.unverified_skills.append(skill)
            promoted_partial.append(skill)
        claimed.add(key)

    claimed = {
        normalize_text(skill)
        for skill in match.matched_skills + match.unverified_skills
    }
    missing = []
    for skill in list(required_skills or []) + list(match.missing_skills):
        key = normalize_text(skill)
        if key and key not in claimed and key not in {
            normalize_text(s) for s in missing
        }:
            missing.append(skill)

    score, relevance = compute_match_score(
        match.matched_skills,
        match.unverified_skills,
        required_skills,
        required_experience,
        candidate_experience,
    )
    final = match.model_copy(
        update={
            "matched_skills": match.matched_skills[:60],
            "unverified_skills": match.unverified_skills[:60],
            "partial_skills": match.unverified_skills[:60],
            "missing_skills": missing[:60],
            "evidence": match.evidence[:20],
            "match_score": score,
            "relevance_score": score / 100,
            "relevance": relevance,
        }
    )
    audit = {
        **audit,
        "promoted_skills": promoted_matched,
        "promoted_partial_skills": promoted_partial,
    }
    return final, audit
