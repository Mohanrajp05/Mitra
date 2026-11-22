import pytest

from app.services.job_search_service import build_job_url, normalize_role


@pytest.mark.parametrize(
    ("source", "role", "location", "expected"),
    [
        ("linkedin", "se", "", "keywords=Software+Engineer&location="),
        ("linkedin", "C++ Developer", "Bengaluru", "keywords=C%2B%2B+Developer&location=Bengaluru"),
        ("naukri", "Data Analyst", "", "data-analyst-jobs"),
        ("naukri", "UI/UX Designer", "New Delhi", "ui-ux-designer-jobs-in-new-delhi"),
        ("naukri", "devops", "Pune", "devops-engineer-jobs-in-pune"),
    ],
)
def test_build_job_url(source, role, location, expected):
    assert expected in build_job_url(source, role, location)


def test_naukri_fallback_uses_query_format():
    url = build_job_url("naukri", "da", "Mumbai", naukri_fallback=True)
    assert url == "https://www.naukri.com/jobs-in-india?k=Data+Analyst&l=Mumbai"


def test_normalize_role_keeps_unknown_role():
    assert normalize_role("UI/UX Designer") == "UI/UX Designer"


def test_invalid_source_and_empty_role_are_rejected(client):
    assert client.get("/job-link", params={"source": "indeed", "role": "se"}).status_code == 400
    assert client.get("/job-link", params={"source": "linkedin", "role": "   "}).status_code == 400
