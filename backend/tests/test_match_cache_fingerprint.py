import datetime as dt
import decimal
import uuid

from app.rag import match_cache


def base_job(**overrides):
    job = {
        "id": "job-1",
        "title": "Backend Engineer",
        "company": "Acme",
        "description": "Build backend services.",
        "required_skills": ["Python", "Kubernetes"],
        "experience_required": 3,
        "location": "Remote",
    }
    job.update(overrides)
    return job


def test_job_fingerprint_accepts_decimal_salary_and_experience_values():
    # Decimal in included fields (experience_required) and extra payload fields
    # (e.g. salary) must not break fingerprinting.
    job = base_job(
        experience_required=decimal.Decimal("3.5"),
        salary_min=decimal.Decimal("90000.00"),
        salary_max=decimal.Decimal("125000.50"),
    )

    fingerprint = match_cache._job_fingerprint(job)

    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 64


def test_job_fingerprint_normalizes_nested_decimal_values():
    # Normalization must be recursive/deterministic for nested Decimal values.
    payload = {
        "experience_required": decimal.Decimal("2.0"),
        "required_skills": ["Python"],
        "compensation": {
            "band": [decimal.Decimal("1000.10"), decimal.Decimal("2000.20")],
            "currency": "USD",
            "meta": {"step": decimal.Decimal("1.500")},
        },
    }
    normalized = match_cache._normalize_fingerprint_value(payload)

    assert normalized["experience_required"] == "2.0"
    assert normalized["compensation"]["band"] == ["1000.10", "2000.20"]
    assert normalized["compensation"]["meta"]["step"] == "1.500"


def test_job_fingerprint_normalizes_uuid_and_datetime_fields():
    job_id = uuid.UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    created_at = dt.datetime(2026, 11, 19, 10, 30, 0, tzinfo=dt.timezone.utc)
    posted_on = dt.date(2026, 11, 19)
    payload = {
        "id": job_id,
        "created_at": created_at,
        "posted_on": posted_on,
        "nested": {"owner_id": job_id, "times": [created_at, posted_on]},
    }

    normalized = match_cache._normalize_fingerprint_value(payload)

    assert normalized["id"] == str(job_id)
    assert normalized["created_at"] == created_at.isoformat()
    assert normalized["posted_on"] == posted_on.isoformat()
    assert normalized["nested"]["owner_id"] == str(job_id)
    assert normalized["nested"]["times"] == [created_at.isoformat(), posted_on.isoformat()]


def test_identical_payloads_produce_identical_fingerprints():
    job_a = base_job(
        experience_required=decimal.Decimal("5.0"),
        salary=decimal.Decimal("120000.00"),
        posted_at=dt.datetime(2026, 11, 19, 9, 0, 0),
        external_id=uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )
    job_b = base_job(
        experience_required=decimal.Decimal("5.0"),
        salary=decimal.Decimal("120000.00"),
        posted_at=dt.datetime(2026, 11, 19, 9, 0, 0),
        external_id=uuid.UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
    )

    assert match_cache._job_fingerprint(job_a) == match_cache._job_fingerprint(job_b)


def test_changed_job_field_produces_different_fingerprint():
    original = base_job(description="Build APIs in Python.")
    changed = base_job(description="Build APIs in Python and Go.")

    assert match_cache._job_fingerprint(original) != match_cache._job_fingerprint(changed)


def test_decimal_experience_change_produces_different_fingerprint():
    original = base_job(experience_required=decimal.Decimal("2.0"))
    changed = base_job(experience_required=decimal.Decimal("3.0"))

    assert match_cache._job_fingerprint(original) != match_cache._job_fingerprint(changed)