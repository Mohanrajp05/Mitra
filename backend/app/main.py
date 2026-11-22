
import asyncio
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar

import psycopg
from anyio import to_thread
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from psycopg_pool import PoolClosed, PoolTimeout

from app.api import auth, candidates, chat, health, interviews, job_search, jobs, notifications, ops, privacy, rag, scheduling
from app.core.config import settings
from app.core.metrics import get_metrics
from app.core.rate_limit import RateLimitExceeded
from app.database.connection import (
    DatabaseNotConfiguredError,
    DatabasePoolUnavailableError,
    close_pool,
    open_pool,
)
from app.rag.document_loader import (
    DocumentError,
    EmptyDocumentError,
    FileTooLargeError,
    UnsupportedFileTypeError,
)
from app.rag.llm import LLMCredentialsError, LLMError, LLMNotConfiguredError
from app.rag.vector_store import InvalidIdentifierError, VectorStoreError
from app.services import chat_service, rag_service
from app.services.guardrails import MessageValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)
logger = logging.getLogger(__name__)

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
SAFE_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


for _handler in logging.getLogger().handlers:
    _handler.addFilter(RequestIdLogFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
   
    try:
        await to_thread.run_sync(open_pool)
        logger.info("Database connection pool initialized.")
    except DatabaseNotConfiguredError:
        logger.warning("DATABASE_URL is not configured; database endpoints will fail.")
    except Exception as exc:
        logger.warning(
            "Database connection pool could not be initialized (%s). "
            "Database endpoints will return 503.",
            type(exc).__name__,
        )

    # Sentence-transformer cold-load takes several seconds on CPU.  Warm it in
    # the background so the first resume upload does not pay that cost while
    # the candidate waits.
    warmup_task = None
    try:
        from app.rag.embeddings import get_embedding_service

        async def _warm_embeddings() -> None:
            started = time.perf_counter()
            try:
                await to_thread.run_sync(get_embedding_service().warm)
                logger.info(
                    "Embedding model warmed in %.2fs.", time.perf_counter() - started
                )
            except Exception as exc:  # noqa: BLE001 - warm-up is best effort
                logger.warning("Embedding model warm-up failed: %s", type(exc).__name__)

        warmup_task = asyncio.create_task(_warm_embeddings())
    except Exception as exc:  # noqa: BLE001 - never block startup
        logger.warning("Embedding warm-up could not be scheduled: %s", type(exc).__name__)

    # Periodically deliver due in-app interview reminders. Claiming is
    # database-backed so multiple workers cannot process the same reminder.
    from app.services import reminder_scheduler

    reminder_scheduler.start_scheduler()

    try:
        yield
    finally:
        await reminder_scheduler.stop_scheduler()
        if warmup_task is not None:
            warmup_task.cancel()
        try:
            close_pool()
            logger.info("Database connection pool closed.")
        except Exception as exc:
            logger.warning("Error while closing database pool: %s", type(exc).__name__)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Phase 1 foundation for the AI Recruitment Agent. "
        "Supabase handles authentication; PostgreSQL stores application data."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.allowed_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID", "Retry-After"],
)


@app.middleware("http")
async def request_tracing_middleware(request: Request, call_next):
    raw_id = request.headers.get("X-Request-ID", "")
    request_id = raw_id if SAFE_REQUEST_ID_PATTERN.match(raw_id) else uuid.uuid4().hex
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled error while handling %s", request.url.path)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        _record_request_metric(request, 500, duration_ms, request_id)
        request_id_var.reset(token)
        return JSONResponse(
            status_code=500,
            headers={"X-Request-ID": request_id},
            content={"detail": "An unexpected error occurred. Please try again."},
        )
    request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    _record_request_metric(request, response.status_code, duration_ms, request_id)
    logger.info(
        "http method=%s path=%s status=%s duration_ms=%s",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


def _record_request_metric(
    request: Request, status_code: int, duration_ms: float, request_id: str
) -> None:
    try:
        get_metrics().record_request(
            request.method, request.url.path, status_code, duration_ms, request_id
        )
    except Exception:
        logger.debug("Request metrics recording failed.", exc_info=True)


@app.exception_handler(DatabaseNotConfiguredError)
async def database_not_configured_handler(
    request: Request, exc: DatabaseNotConfiguredError
):
    logger.error("Database access attempted without DATABASE_URL: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The application database is not configured."},
    )


@app.exception_handler(DatabasePoolUnavailableError)
async def database_pool_unavailable_handler(
    request: Request, exc: DatabasePoolUnavailableError
):
    logger.error("Database pool unavailable while handling %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "The application database is currently unavailable."},
    )


@app.exception_handler(PoolTimeout)
@app.exception_handler(PoolClosed)
async def database_pool_timeout_handler(request: Request, exc):
    logger.error("Database pool exhausted while handling %s", request.url.path)
    return JSONResponse(
        status_code=503,
        content={"detail": "The application database is currently unavailable."},
    )


@app.exception_handler(psycopg.Error)
async def database_error_handler(request: Request, exc: psycopg.Error):
    # Log details on the server, never return them to the browser.
    logger.exception("Database error while handling %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "A database error occurred. Please try again later."},
    )


@app.exception_handler(UnsupportedFileTypeError)
async def unsupported_file_type_handler(request: Request, exc: UnsupportedFileTypeError):
    return JSONResponse(status_code=415, content={"detail": str(exc)})


@app.exception_handler(FileTooLargeError)
async def file_too_large_handler(request: Request, exc: FileTooLargeError):
    return JSONResponse(status_code=413, content={"detail": str(exc)})


@app.exception_handler(EmptyDocumentError)
async def empty_document_handler(request: Request, exc: EmptyDocumentError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


@app.exception_handler(DocumentError)
async def document_error_handler(request: Request, exc: DocumentError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(InvalidIdentifierError)
async def invalid_identifier_handler(request: Request, exc: InvalidIdentifierError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(LLMNotConfiguredError)
async def llm_not_configured_handler(request: Request, exc: LLMNotConfiguredError):
    logger.warning("AI service not configured: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "The AI service is not configured."},
    )


@app.exception_handler(LLMCredentialsError)
async def llm_credentials_error_handler(request: Request, exc: LLMCredentialsError):
    logger.error("AI service credentials rejected: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The AI service is not configured correctly. "
            "Please contact the administrator to fix the AI service settings."
        },
    )


@app.exception_handler(LLMError)
async def llm_error_handler(request: Request, exc: LLMError):
    logger.warning("AI service error: %s", exc)
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc)},
    )


@app.exception_handler(VectorStoreError)
async def vector_store_error_handler(request: Request, exc: VectorStoreError):
    logger.exception("Vector store error while handling %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "A document storage error occurred. Please try again later."},
    )


@app.exception_handler(chat_service.SessionNotFoundError)
async def chat_session_not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(MessageValidationError)
async def message_validation_error_handler(request: Request, exc):
    logger.warning("Chat message rejected: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        headers={"Retry-After": str(exc.retry_after)},
        content={
            "detail": f"{exc} Please try again in about {exc.retry_after} seconds."
        },
    )


@app.exception_handler(chat_service.ChatLimitExceededError)
async def chat_limit_exceeded_handler(request: Request, exc: chat_service.ChatLimitExceededError):
    return JSONResponse(status_code=429, content={"detail": str(exc)})


@app.exception_handler(rag_service.RecordNotFoundError)
async def record_not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(rag_service.RagAgentError)
async def rag_agent_error_handler(request: Request, exc):
    logger.error("RAG agent error: %s", exc)
    reason = str(exc).lower()
    if "rate limited" in reason:
        status_code = 503
        detail = "The AI service is rate limited right now. Please retry in a minute."
    elif "timed out" in reason:
        status_code = 504
        detail = "The AI service timed out. Please retry."
    elif "could not be reached" in reason:
        status_code = 502
        detail = "The AI service could not be reached. Check the network connection and retry."
    elif "ollama is unavailable" in reason:
        status_code = 503
        detail = "Ollama is unavailable. Start Ollama with the configured model, then retry."
    elif "ollama returned" in reason:
        status_code = 502
        detail = "Ollama returned an invalid matching response. Please retry."
    elif "credentials" in reason:
        status_code = 503
        detail = (
            "The AI service credentials are invalid. "
            "Please check the backend AI service configuration."
        )
    elif "not configured" in reason:
        status_code = 503
        detail = (
            "The AI service is not configured. "
            "Add the AI service credentials to the backend environment."
        )
    elif "rejected the request" in reason:
        status_code = 502
        detail = (
            "The AI service rejected the request. "
            "Check the model and provider configuration."
        )
    else:
        status_code = 502
        detail = "The AI analysis could not be completed. Please try again."
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(rag_service.RagServiceError)
async def rag_service_error_handler(request: Request, exc):
    logger.warning("RAG service error: %s", exc)
    return JSONResponse(status_code=400, content={"detail": str(exc)})


app.include_router(health.router)
app.include_router(job_search.router)
app.include_router(auth.router)
app.include_router(jobs.router)
app.include_router(candidates.router)
app.include_router(rag.router)
app.include_router(chat.router)
app.include_router(interviews.router)
app.include_router(scheduling.router)
app.include_router(notifications.router)
app.include_router(ops.router)
app.include_router(privacy.router)


@app.get("/health", include_in_schema=False)
def root_health_alias():
    """Root-level alias for external monitors that probe /health without the
    /api prefix (they previously logged a 404 every 30 seconds)."""
    return health.health_check()


@app.get("/", include_in_schema=False)
def root():
    return {
        "message": "AI Recruitment Agent API",
        "docs": "/docs",
        "health": "/api/health",
    }


