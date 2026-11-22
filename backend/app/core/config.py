
import os
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")

    
def _first_env(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _split_origins(value: str) -> tuple[str, ...]:
    return tuple(
        origin.strip().rstrip("/")
        for origin in value.split(",")
        if origin.strip()
    )


@dataclass(frozen=True)
class Settings:
    database_url: str
    supabase_url: str
    supabase_publishable_key: str
    frontend_origin: str
    app_name: str = "AI Recruitment Agent API"
    app_version: str = "1.0.0"
    # repr=False prevents credentials from appearing in logs or tracebacks.
    smtp_email: str = field(default="", repr=False)
    smtp_password: str = field(default="", repr=False)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_use_tls: bool = True
    email_claim_timeout_minutes: int = 5
    email_retry_delay_minutes: int = 15

    @property
    def smtp_configured(self) -> bool:
        return bool(
            self.smtp_email
            and self.smtp_password
            and self.smtp_host
            and 0 < self.smtp_port < 65536
        )

    @property
    def allowed_origins(self) -> tuple[str, ...]:
        origins = list(_split_origins(self.frontend_origin)) or ["http://localhost:5173"]

        for origin in tuple(origins):
            parsed = urlsplit(origin)
            if parsed.hostname not in {"localhost", "127.0.0.1"}:
                continue
            host = "127.0.0.1" if parsed.hostname == "localhost" else "localhost"
            port = f":{parsed.port}" if parsed.port else ""
            counterpart = f"{parsed.scheme}://{host}{port}"
            if counterpart not in origins:
                origins.append(counterpart)

        return tuple(origins)

    @property
    def database_configured(self) -> bool:
        return bool(self.database_url)

    @property
    def auth_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_publishable_key)


settings = Settings(
    database_url=_first_env("DATABASE_URL"),
    supabase_url=_first_env("SUPABASE_URL", "VITE_SUPABASE_URL").rstrip("/"),
    supabase_publishable_key=_first_env(
        "SUPABASE_PUBLISHABLE_KEY", "VITE_SUPABASE_PUBLISHABLE_KEY"
    ),
    frontend_origin=_first_env("FRONTEND_ORIGIN") or "http://localhost:5173",
    smtp_email=_first_env("SMTP_EMAIL"),
    # Gmail displays App Passwords as "xxxx xxxx xxxx xxxx"; SMTP needs the
    # 16 characters without the display spaces.
    smtp_password=_first_env("SMTP_PASSWORD").replace(" ", ""),
    smtp_host=_first_env("SMTP_HOST") or "smtp.gmail.com",
    smtp_port=_int_env("SMTP_PORT", 587),
    smtp_use_tls=_first_env("SMTP_USE_TLS", "true").lower() not in {"0", "false", "no", "off"},
    email_claim_timeout_minutes=_int_env("EMAIL_CLAIM_TIMEOUT_MINUTES", 5),
    email_retry_delay_minutes=_int_env("EMAIL_RETRY_DELAY_MINUTES", 15),
)








