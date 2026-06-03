from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from funnelhub.api.auth import router as auth_router
from funnelhub.api.email import router as email_router
from funnelhub.api.inbox import router as inbox_router
from funnelhub.api.messenger import router as messenger_router
from funnelhub.api.webhooks import router as webhooks_router
from funnelhub.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.app_debug)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(auth_router)
    app.include_router(email_router)
    app.include_router(inbox_router)
    app.include_router(messenger_router)
    app.include_router(webhooks_router)
    mount_inbox_app(app)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app


def mount_inbox_app(app: FastAPI) -> None:
    dist_path = Path(__file__).resolve().parents[2] / "inbox-app" / "dist"
    index_path = dist_path / "index.html"
    assets_path = dist_path / "assets"
    if not index_path.exists():
        return

    if assets_path.exists():
        app.mount(
            "/inbox/assets",
            StaticFiles(directory=assets_path),
            name="inbox-assets",
        )

    @app.get("/inbox", include_in_schema=False)
    @app.get("/inbox/", include_in_schema=False)
    async def inbox_index() -> FileResponse:
        return FileResponse(index_path)

    @app.get("/inbox/{path:path}", include_in_schema=False)
    async def inbox_spa(path: str) -> FileResponse:
        file_path = dist_path / path
        if path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(index_path)


app = create_app()
