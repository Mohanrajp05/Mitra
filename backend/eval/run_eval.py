
import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from pathlib import Path

import httpx

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import load_dotenv  # noqa: E402

load_dotenv(BACKEND_DIR / ".env")

from app.rag.agents.candidate_matching_agent import CandidateMatchingAgent  # noqa: E402
from app.rag.agents.matching_postcheck import finalize_match  # noqa: E402
from app.rag.ollama import OllamaError, get_ollama_client  # noqa: E402
from app.schemas.rag import MatchResult  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent
CASES_PATH = EVAL_DIR / "cases.json"

WEAK_CONTEXT_PATTERN = re.compile(
    r"(?:familiar(?:ity)? with|exposure to|aware(?:ness)? of|"
    r"heard (?:of|about)|read (?:of|about|the)|watched|attending|attended|"
    r"(?:completed|followed|took|taking|enrolled in)\s+(?:a|an|one|the)?\s*"
    r"(?:\w+\s+){0,4}(?:course|workshop|tutorial|webinar|bootcamp|class|series)|"
    r"coursework|tutorial|webinar|bootcamp|"
    r"lists? .{0,50} under|explor(?:e|ed|ing)|studied (?:for|the)|"
    r"bookmarks?|knows? (?:what|the term)|"
    r"only for (?:simple|basic)|copied from|pair-programmed|"
    r"selenium ide|recordings?|shadowed|user stories|sat in|demos|"
    r"in every proposal deck|built by (?:the )?client teams|"
    r"interviewed engineers about)",
    re.IGNORECASE,
)

NEGATION_PATTERN = re.compile(
    r"\b(?:no|not|never|without|zero|none)\b[^.;]{0,50}$", re.IGNORECASE
)

SKILL_ALIASES = {
    "node.js": ["nodejs", "node js", "node"],
    "node": ["nodejs", "node.js"],
    "ci/cd": ["ci cd", "ci-cd", "continuous integration", "continuous delivery"],
    "apache spark": ["spark"],
    "api documentation": ["api docs", "documenting apis", "openapi"],
    "developer tools": ["postman", "curl", "dev tools"],
    "usability testing": ["usability tests", "usability sessions", "user testing"],
    "lead generation": ["outbound prospecting", "prospecting"],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def skill_in_text(skill: str, normalized_resume: str) -> bool:
    needle = normalize_text(skill)
    if not needle:
        return False
    if needle in normalized_resume:
        return True
    aliases = SKILL_ALIASES.get(needle, [])
    return any(alias in normalized_resume for alias in aliases)


def skill_status(skill: str, resume_text: str) -> str:
    
    normalized = normalize_text(resume_text)
    needle = normalize_text(skill)
    if not needle:
        return "none"

    spans: list[tuple[int, int]] = []
    for variant in [needle, *SKILL_ALIASES.get(needle, [])]:
        for match in re.finditer(re.escape(variant), normalized):
            spans.append((match.start(), match.end()))
    if not spans:
        return "none"

    strong = False
    negated = 0
    for start, end in spans:
        before = normalized[max(0, start - 90) : start]
        window = before + " " + normalized[end : end + 40]
        if NEGATION_PATTERN.search(before):
            negated += 1
            continue
        if WEAK_CONTEXT_PATTERN.search(window):
            continue
        strong = True
        break

    if strong:
        return "strong"
    if negated == len(spans):
        return "negated"
    return "weak"


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


def apply_match_postcheck(match: MatchResult, resume_text: str, required: list[str]) -> tuple[MatchResult, dict]:
    normalized_resume = normalize_text(resume_text)
    dropped_skills = []
    dropped_quotes = 0

    verified_matched = []
    unverified = list(match.unverified_skills)
    for skill in match.matched_skills:
        if skill_in_text(skill, normalized_resume):
            verified_matched.append(skill)
        else:
            if skill not in unverified:
                unverified.append(skill)
            dropped_skills.append(skill)

    verified_quotes = []
    for item in match.evidence:
        if quote_in_text(item.quote, normalized_resume):
            verified_quotes.append(item)
        else:
            dropped_quotes += 1

    claimed = {normalize_text(s) for s in verified_matched + unverified}
    missing = []
    for skill in required:
        if normalize_text(skill) not in claimed:
            missing.append(skill)
    for skill in match.missing_skills:
        if normalize_text(skill) not in claimed and normalize_text(skill) not in {normalize_text(s) for s in missing}:
            missing.append(skill)

    postchecked = MatchResult(
        matched_skills=verified_matched,
        missing_skills=missing,
        unverified_skills=unverified,
        relevance_score=match.relevance_score,
        relevance=match.relevance,
        explanation=match.explanation,
        evidence=verified_quotes,
    )
    audit = {
        "dropped_skills": dropped_skills,
        "dropped_quotes": dropped_quotes,
    }
    return postchecked, audit


class OfflineMatcherV1:
    name = "offline-v1"

    async def match(self, job, resume_text, runs=1):
        required = job["required_skills"]
        normalized_resume = normalize_text(resume_text)
        matched = [s for s in required if skill_in_text(s, normalized_resume)]
        missing = [s for s in required if s not in matched]
        matched_ratio = len(matched) / len(required) if required else 0.0
        score = round(matched_ratio, 4)
        return [
            MatchResult(
                matched_skills=matched,
                missing_skills=missing,
                unverified_skills=[],
                relevance_score=score,
                relevance="strong" if score >= 0.75 else "moderate" if score >= 0.45 else "weak",
                explanation="Deterministic offline scoring based on skill presence.",
                evidence=[],
            )
        ]


class OfflineMatcherV2:
    name = "offline-v2"

    async def match(self, job, resume_text, runs=1):
        required = job["required_skills"]
        matched = []
        unverified = []
        for skill in required:
            status = skill_status(skill, resume_text)
            if status == "strong":
                matched.append(skill)
            elif status == "weak":
                unverified.append(skill)
        missing = [s for s in required if s not in matched and s not in unverified]
        matched_ratio = len(matched) / len(required) if required else 0.0
        unverified_ratio = len(unverified) / len(required) if required else 0.0
        score = round(matched_ratio * 0.9 + unverified_ratio * 0.25, 4)
        base = MatchResult(
            matched_skills=matched,
            missing_skills=missing,
            unverified_skills=unverified,
            relevance_score=score,
            relevance="strong" if score >= 0.75 else "moderate" if score >= 0.45 else "weak",
            explanation="Offline scoring with weak-context demotion.",
            evidence=[],
        )
        postchecked, _audit = apply_match_postcheck(base, resume_text, required)
        return [postchecked]


class LiveMatcher:
    name = "live-agent"

    def __init__(
        self,
        pace: float = 5.0,
        retries: int = 6,
        cache_path: Path | None = None,
        prompt_version: str = "current",
    ) -> None:
        # Match scoring is intentionally local-only, exactly like the app's
        # match endpoint: every score comes from the local Ollama model and
        # the Portkey gateway is never used. The match agent always uses its
        # designed local system prompt -- the legacy Portkey-era prompt does
        # not fit the local contract and makes the model return invalid JSON.
        self.match_agent = CandidateMatchingAgent()
        self._ollama = get_ollama_client()
        self._retries = max(1, retries)
        self._cache_path = cache_path
        self._cache: dict[str, dict] = {}
        self._counters: dict[str, int] = {}
        self._prompt_version = prompt_version
        if cache_path and cache_path.exists():
            try:
                self._cache = json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._cache = {}

    def _key(self, kind: str, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self._prompt_version}:{kind}:{digest}"

    def _remember(self, key: str, value: dict) -> None:
        self._cache[key] = value
        if self._cache_path:
            try:
                self._cache_path.write_text(
                    json.dumps(self._cache), encoding="utf-8"
                )
            except OSError:
                pass

    async def _local_match(self, job: dict, resume_text: str) -> MatchResult:
        """Score the candidate with the local Ollama model, mirroring the app.

        Uses the same local contract as rag_service.match_candidate
        (match_score 0-100, partial_skills, experience_comparison) and maps
        the result onto MatchResult for the evaluation pipeline.
        """
        last_error: Exception | None = None
        local = None
        for attempt in range(self._retries):
            if attempt > 0:
                await asyncio.sleep(min(30.0, 5.0 * (2 ** (attempt - 1))))
            try:
                local = await self.match_agent.match_locally(
                    self._ollama,
                    job_text=f"{job['title']}\n{job['description']}",
                    required_skills=list(job["required_skills"]),
                    required_experience=job.get("experience_required"),
                    resume_text=resume_text,
                    candidate_experience=None,
                )
                break
            except OllamaError as exc:
                last_error = exc
        if local is None:
            raise last_error if last_error else RuntimeError("Local match failed.")

        # Mirror the app: verify claims, promote overlooked demonstrable
        # skills, and recompute the score deterministically from the
        # validated lists instead of trusting the model's score.
        final, _audit = finalize_match(
            local,
            resume_text,
            list(job["required_skills"]),
            job.get("experience_required"),
            candidate_experience=None,
        )
        return final

    async def match(self, job: dict, resume_text: str, runs: int = 3) -> list[MatchResult]:
        job_text = f"{job['title']}\n{job['description']}"
        job_key = self._key("job", job_text)
        resume_key = self._key("resume", resume_text)
        pair_key = f"{job_key}:{resume_key}"
        start = self._counters.get(pair_key, 0)
        self._counters[pair_key] = start + max(1, runs)

        results: list[MatchResult] = []
        for offset in range(max(1, runs)):
            # Key includes the local model so cached Portkey-era match results
            # are never reused: scores must come from Ollama from now on.
            run_key = f"match:{self._ollama.settings.model}:{pair_key}:{start + offset}"
            if run_key in self._cache:
                results.append(MatchResult.model_validate(self._cache[run_key]))
                continue
            single = await self._local_match(job, resume_text)
            self._remember(run_key, single.model_dump())
            results.append(single)
        return results


def rank_candidates(results: dict[str, list[MatchResult]]) -> list[tuple[str, float]]:
    ranked = []
    for name, runs in results.items():
        mean_score = sum(r.relevance_score for r in runs) / len(runs)
        ranked.append((name, mean_score))
    return sorted(ranked, key=lambda item: (-item[1], item[0]))


def evaluate_case(case: dict, matcher, runs: int) -> dict:
    job = case["job"]
    per_candidate = {}
    failures = []

    async def run_candidate(candidate: dict):
        raw_runs = []
        checked_runs = []
        audits = []
        errors = []
        for _ in range(max(1, runs)):
            try:
                batch = await matcher.match(job, candidate["resume_text"], runs=1)
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                continue
            single = batch[0]
            postchecked, audit = apply_match_postcheck(
                single, candidate["resume_text"], job["required_skills"]
            )
            raw_runs.append(single)
            checked_runs.append(postchecked)
            audits.append(audit)
        return raw_runs, checked_runs, audits, errors

    loop = asyncio.new_event_loop()
    try:
        for candidate in case["candidates"]:
            raw_runs, checked_runs, audits, errors = loop.run_until_complete(
                run_candidate(candidate)
            )
            per_candidate[candidate["name"]] = {
                "runs": checked_runs,
                "raw_scores": [r.relevance_score for r in raw_runs],
                "raw": raw_runs[0] if raw_runs else None,
                "audits": audits,
                "errors": errors,
                "expected": candidate,
            }
            if errors:
                failures.append({"candidate": candidate["name"], "errors": errors})
    finally:
        loop.close()

    ranked = rank_candidates(
        {name: data["runs"] for name, data in per_candidate.items() if data["runs"]}
    )
    top_score = ranked[0][1] if ranked else None
    top_names = {name for name, score in ranked if score == top_score}
    expected_ranks = {
        candidate["name"]: candidate.get("expected_rank")
        for candidate in case["candidates"]
    }
    expected_top = next(
        (
            name
            for name, rank in expected_ranks.items()
            if rank == 1
        ),
        case.get("expected_top_candidate", ""),
    )

    def top_is_correct(names: set[str]) -> bool:
        if not expected_top or expected_top not in names:
            return False
        return all(expected_ranks.get(name) == 1 for name in names)

    rank_correct = top_is_correct(top_names)

    max_runs = max((len(data["runs"]) for data in per_candidate.values()), default=0)
    rank_stable = False
    if max_runs:
        rank_stable = True
        for index in range(max_runs):
            snapshot = {
                name: [data["runs"][index]]
                for name, data in per_candidate.items()
                if len(data["runs"]) > index
            }
            if not snapshot:
                continue
            snapshot_ranked = rank_candidates(snapshot)
            snapshot_top = snapshot_ranked[0][1]
            snapshot_names = {
                name for name, score in snapshot_ranked if score == snapshot_top
            }
            if not top_is_correct(snapshot_names):
                rank_stable = False
                break

    spreads = [
        max(r.relevance_score for r in data["runs"]) - min(r.relevance_score for r in data["runs"])
        for data in per_candidate.values()
        if data["runs"]
    ]
    mean_spread = sum(spreads) / len(spreads) if spreads else 0.0

    matched_hits = matched_total = 0
    missing_hits = missing_total = 0
    hallucinated_skills = 0
    dropped_quotes = 0
    for name, data in per_candidate.items():
        if not data["runs"]:
            continue
        expected = data["expected"]
        first = data["runs"][0]
        expected_matched = set(normalize_text(s) for s in expected["expected_matched_skills"])
        got_matched = set(normalize_text(s) for s in first.matched_skills)
        matched_hits += len(got_matched & expected_matched)
        matched_total += len(got_matched)
        expected_missing = set(normalize_text(s) for s in expected["expected_missing_skills"])
        got_missing = set(normalize_text(s) for s in first.missing_skills)
        missing_hits += len(got_missing & expected_missing)
        missing_total += len(got_missing)
        hallucinated_skills += sum(len(audit["dropped_skills"]) for audit in data["audits"])
        dropped_quotes += sum(audit["dropped_quotes"] for audit in data["audits"])

    return {
        "case_id": case["case_id"],
        "expected_top": expected_top,
        "ranked": [{"name": name, "score": round(score, 4)} for name, score in ranked],
        "rank_correct": rank_correct,
        "rank_stable": rank_stable,
        "complete": len(ranked) >= 2,
        "failed_candidates": failures,
        "mean_spread": round(mean_spread, 4),
        "per_candidate": {
            name: {
                "scores": [round(r.relevance_score, 4) for r in data["runs"]],
                "matched": data["runs"][0].matched_skills if data["runs"] else [],
                "missing": data["runs"][0].missing_skills if data["runs"] else [],
                "unverified": data["runs"][0].unverified_skills if data["runs"] else [],
                "explanation": data["runs"][0].explanation if data["runs"] else "",
                "dropped_by_postcheck": data["audits"],
                "errors": data["errors"],
                "expected_matched": data["expected"]["expected_matched_skills"],
                "expected_missing": data["expected"]["expected_missing_skills"],
            }
            for name, data in per_candidate.items()
        },
        "skill_metrics": {
            "matched_hits": matched_hits,
            "matched_total": matched_total,
            "missing_hits": missing_hits,
            "missing_total": missing_total,
        },
        "hallucinated_skills": hallucinated_skills,
        "quotes_failing_check": dropped_quotes,
    }


def aggregate(results: list[dict]) -> dict:
    cases = len(results)
    completed = [r for r in results if r["complete"]]
    scored = completed if completed else results
    rank_correct = sum(1 for r in scored if r["rank_correct"])
    rank_stable = sum(1 for r in scored if r["rank_stable"])
    spreads = [r["mean_spread"] for r in scored]
    matched_hits = sum(r["skill_metrics"]["matched_hits"] for r in results)
    matched_total = sum(r["skill_metrics"]["matched_total"] for r in results)
    missing_hits = sum(r["skill_metrics"]["missing_hits"] for r in results)
    missing_total = sum(r["skill_metrics"]["missing_total"] for r in results)
    hallucinated = sum(r["hallucinated_skills"] for r in results)
    dropped_quotes = sum(r["quotes_failing_check"] for r in results)
    failed_candidates = sum(len(r["failed_candidates"]) for r in results)
    failed_calls = sum(
        len(failure["errors"])
        for r in results
        for failure in r["failed_candidates"]
    )
    return {
        "cases": cases,
        "completed_cases": len(completed),
        "failed_cases": [r["case_id"] for r in results if not r["complete"]],
        "failed_candidates": failed_candidates,
        "failed_llm_calls": failed_calls,
        "ranking_accuracy": round(rank_correct / len(scored), 3) if scored else None,
        "ranking_stability": round(rank_stable / len(scored), 3) if scored else None,
        "mean_score_spread": round(sum(spreads) / len(spreads), 4) if spreads else None,
        "matched_precision": round(matched_hits / matched_total, 3) if matched_total else None,
        "missing_precision": round(missing_hits / missing_total, 3) if missing_total else None,
        "matched_hits": matched_hits,
        "matched_total": matched_total,
        "missing_hits": missing_hits,
        "missing_total": missing_total,
        "hallucinated_skills": hallucinated,
        "quotes_failing_check": dropped_quotes,
    }


def print_summary(mode: str, matcher_name: str, results: list[dict], summary: dict) -> None:
    print(f"\n=== Candidate matching evaluation - mode={mode} matcher={matcher_name} ===")
    header = f"{'case':28} {'top1 ok':8} {'stable':7} {'spread':7} {'halluc':7} {'mP':6} {'mR':6}"
    print(header)
    print("-" * len(header))
    expected_totals = {"matched": 0, "missing": 0}
    for r in results:
        m = r["skill_metrics"]
        mp = m["matched_hits"] / m["matched_total"] if m["matched_total"] else float("nan")
        expected_matched_count = sum(
            len(data["expected_matched"])
            for data in r["per_candidate"].values()
        )
        mr = m["matched_hits"] / expected_matched_count if expected_matched_count else float("nan")
        expected_totals["matched"] += expected_matched_count
        print(
            f"{r['case_id']:28} {str(r['rank_correct']):8} {str(r['rank_stable']):7} "
            f"{r['mean_spread']:<7.3f} {r['hallucinated_skills']:<7} {mp:<6.2f} {mr:<6.2f}"
        )
    print("-" * len(header))
    print(
        f"Ranking accuracy : {summary['ranking_accuracy']}"
        f"  (expected top candidate first)"
    )
    print(f"Ranking stability: {summary['ranking_stability']}  (top pick same in all runs)")
    print(f"Mean score spread: {summary['mean_score_spread']}  (3 runs per candidate)")
    print(f"Matched precision: {summary['matched_precision']}  ({summary['matched_hits']}/{summary['matched_total']} claims correct)")
    print(
        f"Missing precision: {summary['missing_precision']}  "
        f"({summary['missing_hits']}/{summary['missing_total']})"
    )
    print(f"Hallucinated skills: {summary['hallucinated_skills']} claims not found in resume text")
    print(f"Quotes failing text check: {summary['quotes_failing_check']}")
    print(f"Completed cases   : {summary['completed_cases']}/{summary['cases']}")
    if summary["failed_cases"]:
        print(f"Failed cases      : {', '.join(summary['failed_cases'])}")
    print(
        f"Agent failures    : {summary['failed_llm_calls']} failed calls across "
        f"{summary['failed_candidates']} candidates"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the candidate matching agent.")
    parser.add_argument("--mode", choices=["auto", "live", "offline"], default="auto")
    parser.add_argument("--matcher", choices=["v1", "v2"], default="v1", help="offline matcher version")
    parser.add_argument("--runs", type=int, default=3, help="consistency runs per candidate")
    parser.add_argument("--pace", type=float, default=5.0, help="kept for CLI compatibility (local Ollama calls are not rate limited)")
    parser.add_argument("--retries", type=int, default=6, help="retries per live gateway call")
    parser.add_argument("--fresh", action="store_true", help="ignore the live response cache")
    parser.add_argument(
        "--prompt",
        choices=["current", "legacy"],
        default="current",
        help="matching agent prompt version (legacy = pre-Phase-4 baseline)",
    )
    parser.add_argument("--out", default=str(EVAL_DIR / "results.json"))
    args = parser.parse_args()

    ollama = get_ollama_client()
    mode = args.mode
    if mode == "auto" or mode == "live":
        try:
            response = httpx.get(f"{ollama.settings.base_url}/api/tags", timeout=5)
            ollama_ok = response.status_code == 200
        except httpx.HTTPError:
            ollama_ok = False
        if not ollama_ok:
            if mode == "live":
                print(
                    f"Ollama is not reachable at {ollama.settings.base_url}. "
                    "Falling back to offline mode."
                )
            mode = "offline"

    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]
    started = time.perf_counter()

    if mode == "live":
        cache_path = None if args.fresh else Path(args.out).with_suffix(".cache.json")
        matcher = LiveMatcher(
            pace=args.pace,
            retries=args.retries,
            cache_path=cache_path,
            prompt_version=args.prompt,
        )
    else:
        matcher = OfflineMatcherV2() if args.matcher == "v2" else OfflineMatcherV1()

    results = [evaluate_case(case, matcher, runs=args.runs) for case in cases]
    summary = aggregate(results)
    summary["mode"] = mode
    summary["matcher"] = (
        matcher.name if mode == "offline" else f"live-agent-{args.prompt}"
    )
    summary["prompt_version"] = args.prompt if mode == "live" else "n/a"
    summary["runs_per_candidate"] = args.runs
    summary["elapsed_seconds"] = round(time.perf_counter() - started, 1)

    payload = {"summary": summary, "results": results}
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print_summary(mode, summary["matcher"], results, summary)
    print(f"\nSaved results to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
