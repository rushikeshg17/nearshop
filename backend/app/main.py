"""NearShop API entry point."""
import logging
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.ai.semantic_index import index
from app.api.router import api_router
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.errors import AppError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("nearshop")
logging.getLogger("apscheduler").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.environment != "development" and settings.secret_key == "dev-only-change-me":
        raise RuntimeError("Set NEARSHOP_SECRET_KEY before running outside development")
    settings.media_dir.mkdir(parents=True, exist_ok=True)
    scheduler = None
    if settings.enable_scheduler:
        from app.jobs import start_scheduler

        scheduler = start_scheduler()
    # Build the semantic index in the background so the first search is fast.
    def warm():
        try:
            with SessionLocal() as db:
                index.ensure(db)
            log.info("semantic index ready: %d listings via %s", len(index.product_ids), index.provider_name)
        except Exception as exc:  # the app still works on keyword search
            log.warning("semantic index warm-up failed: %s", exc)

    threading.Thread(target=warm, daemon=True).start()
    yield
    if scheduler:
        scheduler.shutdown(wait=False)


app = FastAPI(title="NearShop API", version="1.0.0", lifespan=lifespan,
              description="Hyperlocal inventory discovery: find it nearby, reserve, pick up or get it delivered.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["content-type", "x-nearshop-client", "authorization"],
)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse({"error": {"code": exc.code, "message": exc.message}}, status_code=exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    field = ".".join(str(x) for x in first.get("loc", [])[1:]) or "request"
    message = first.get("msg", "Invalid input").removeprefix("Value error, ")
    return JSONResponse(
        {"error": {"code": "validation_error", "message": f"{field}: {message}", "field": field,
                   "details": [{"loc": e.get("loc"), "msg": e.get("msg")} for e in exc.errors()]}},
        status_code=422,
    )


@app.get("/api/health")
def health():
    return {"ok": True}


app.include_router(api_router)
app.mount("/media", StaticFiles(directory=settings.media_dir, check_dir=False), name="media")
