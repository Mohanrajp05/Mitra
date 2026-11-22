from pydantic import BaseModel


class JobPostingExtraction(BaseModel):
    """Structured check for one raw web-search result."""

    is_single_posting: bool
    title: str | None = None
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    apply_url: str | None = None
