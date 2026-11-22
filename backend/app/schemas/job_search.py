from pydantic import BaseModel, Field


class JobPostingExtraction(BaseModel):
    """Structured check for one raw web-search result."""

    is_single_posting: bool
    title: str | None = None
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    apply_url: str | None = None


class CompanyHiringItem(BaseModel):
    company: str | None = None
    role: str | None = None
    career_page_url: str | None = None


class CompanyHiringExtraction(BaseModel):
    """Companies that appear to be hiring for a role."""

    companies: list[CompanyHiringItem] = Field(default_factory=list)
