import os
from contextlib import asynccontextmanager

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from pathwayai_backend.api import router
from pathwayai_backend.config import Settings, get_settings
from pathwayai_backend.core.logging import configure_logging
from pathwayai_backend.core.middleware import RequestContextMiddleware
from pathwayai_backend.db.session import Database
from pathwayai_backend.integrations.base import IntegrationError
from pathwayai_backend.llm.gateway import ModelUnavailableError

load_dotenv()


def configure_langsmith(settings: Settings) -> None:
    if not settings.langsmith_tracing:
        return
    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = (
            settings.langsmith_api_key.get_secret_value()
        )


def create_app(settings: Settings | None = None) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(
        app_settings.log_level, json_logs=app_settings.is_production
    )
    configure_langsmith(app_settings)
    database = Database(app_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        errors = app_settings.validate_runtime_secrets()
        if errors:
            raise RuntimeError("; ".join(errors))
        yield
        await database.close()

    application = FastAPI(
        title=app_settings.app_name,
        version="0.2.0",
        description=(
            "Production-oriented backend for an agentic technical mentor with "
            "LangGraph, Telegram, Neon PostgreSQL, Groq, and Hugging Face."
        ),
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.database = database
    application.add_middleware(RequestContextMiddleware)
    application.include_router(router)

    @application.exception_handler(IntegrationError)
    async def integration_error_handler(_, exc: IntegrationError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @application.exception_handler(ModelUnavailableError)
    async def model_error_handler(_, exc: ModelUnavailableError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    return application


app = create_app()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "pathwayai_backend.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.app_env == "development",
        log_level=settings.log_level.lower(),
    )
