"""Ask the Archive — FastAPI application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import engine, keepalive

logger = setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Ask the Archive starting — region=%s", settings.aws_region)
    async with keepalive():
        yield
    await engine.dispose()
    logger.info("Ask the Archive stopped")


app = FastAPI(
    title="Ask the Archive",
    description=(
        "Enterprise document intelligence with permission-scoped retrieval, "
        "cited answers and honest abstention."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


from app.modules.admin.router import router as admin_router  # noqa: E402
from app.modules.auth.router import router as auth_router  # noqa: E402
from app.modules.chat.router import router as chat_router  # noqa: E402
from app.modules.documents.router import router as documents_router  # noqa: E402
from app.modules.search.router import router as search_router  # noqa: E402
from app.modules.summaries.router import router as summaries_router  # noqa: E402

app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(chat_router)
app.include_router(summaries_router)
app.include_router(search_router)
app.include_router(admin_router)


@app.get("/api/v1/health")
async def health():
    """Liveness plus the provider configuration actually in use."""
    return {
        "status": "ok",
        "providers": {
            "storage": settings.storage_impl,
            "extractor": settings.extractor_impl,
            "embedder": settings.embedder_impl,
            "llm": settings.llm_impl,
            "bedrock_model": settings.bedrock_model_id,
        },
    }
