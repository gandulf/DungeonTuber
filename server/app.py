"""FastAPI application factory."""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from core.lights import light_registry
from core.utils import get_current_version
from server.auth import websocket_authenticated
from server.config import ServerConfig, configure, get_config
from server.events import hub
from server.jobs import analysis_queue, import_queue
from server.routes import analysis, auth, effects, library, lights, settings, storages

logger = logging.getLogger(__file__)


def default_web_dir() -> Path:
    return Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    hub.bind_loop(asyncio.get_running_loop())
    settings.apply_locale()
    light_registry.load()
    yield
    light_registry.save()
    analysis_queue.shutdown()
    import_queue.shutdown()


def create_app(config: ServerConfig | None = None) -> FastAPI:
    if config is not None:
        configure(config)
    config = get_config()

    app = FastAPI(title="DungeonTuber", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(GZipMiddleware, minimum_size=2048)

    for module in (auth, library, settings, effects, analysis, lights, storages):
        app.include_router(module.router)

    @app.get("/api/health", include_in_schema=False)
    def health():
        return {"status": "ok", "version": get_current_version()}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        if not websocket_authenticated(websocket):
            await websocket.close(code=4401)
            return
        await hub.connect(websocket)
        try:
            while True:
                await websocket.receive_text()  # keep-alive pings from the client
        except WebSocketDisconnect:
            pass
        finally:
            hub.disconnect(websocket)

    web_dir = config.web_dir or default_web_dir()
    index_file = web_dir / "index.html"
    if (web_dir / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=web_dir / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        if full_path.startswith(("api/", "media/")):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        candidate = (web_dir / full_path).resolve() if full_path else None
        if candidate and candidate.is_file() and candidate.is_relative_to(web_dir.resolve()):
            return FileResponse(candidate)
        if index_file.is_file():
            return FileResponse(index_file, headers={"Cache-Control": "no-cache"})
        return JSONResponse({"detail": "Web frontend not built. Run 'npm run build' in web/."}, status_code=404)

    return app
