"""FastAPI application: the API, the mock target system, and the UI."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import mock_target
from app.api import router as api_router
from app.graph import build_graph, open_async_checkpointer
from app.settings import ROOT, get_settings
from app.store import Store, configure_store

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

WEB_DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)

    store = Store(settings.db_path)
    configure_store(store)

    checkpointer = await open_async_checkpointer(settings.checkpoint_path)
    app.state.store = store
    app.state.checkpointer = checkpointer
    app.state.graph = build_graph(checkpointer)
    log.info("Ready. Data in %s, checkpoints in %s", settings.db_path, settings.checkpoint_path)
    try:
        yield
    finally:
        store.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="HR Work Automation",
        description="Autonomous HR data migration with a human escalation boundary",
        lifespan=lifespan,
    )
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(mock_target.router)

    if WEB_DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(WEB_DIST / "index.html")

    else:

        @app.get("/")
        async def index_placeholder() -> dict:
            return {
                "status": "the API is running, the UI is not built yet",
                "build_ui": "cd web && npm install && npm run build",
                "api_docs": "/docs",
            }

    return app


app = create_app()
