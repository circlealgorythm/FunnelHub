from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from funnelhub.api.auth import router as auth_router
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
    app.include_router(inbox_router)
    app.include_router(messenger_router)
    app.include_router(webhooks_router)

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": settings.app_name}

    return app


app = create_app()
