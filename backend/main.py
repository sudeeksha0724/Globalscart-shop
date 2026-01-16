from __future__ import annotations

import logging
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from starlette.requests import Request
from fastapi.staticfiles import StaticFiles

from .routes.addresses import router as addresses_router
from .routes.api_admin import router as api_admin_router
from .routes.api_auth import router as api_auth_router
from .routes.api_config import router as api_config_router
from .routes.api_customer import router as api_customer_router
from .routes.api_events import router as api_events_router
from .analytics.admin_analytics import router as admin_analytics_router


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

app = FastAPI(title="GlobalCart Demo API")

_log = logging.getLogger("globalcart")
if not _log.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    _log.info("rid=%s method=%s path=%s status=%s", rid, request.method, request.url.path, response.status_code)
    return response


@app.middleware("http")
async def shop_html_no_cache_middleware(request: Request, call_next):
    try:
        path = request.url.path or ""
        is_shop_html = (
            request.method == "GET"
            and (path == "/shop" or path == "/shop/" or (path.startswith("/shop/") and path.endswith(".html")))
        )
        if is_shop_html:
            # Prevent stale cached HTML for the shop UI (especially on mobile) so changes like
            # updated script version query params take effect immediately.
            hdrs = list(request.scope.get("headers") or [])
            hdrs = [
                (k, v)
                for (k, v) in hdrs
                if k.lower() not in (b"if-none-match", b"if-modified-since")
            ]
            request.scope["headers"] = hdrs
    except Exception:
        pass

    response = await call_next(request)
    try:
        path = request.url.path or ""
        is_shop_html = (
            request.method == "GET"
            and (path == "/shop" or path == "/shop/" or (path.startswith("/shop/") and path.endswith(".html")))
        )
        if is_shop_html:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers.pop("ETag", None)
            response.headers.pop("Last-Modified", None)
    except Exception:
        pass
    return response


@app.middleware("http")
async def admin_no_cache_middleware(request: Request, call_next):
    try:
        path = request.url.path or ""
        if request.method == "GET" and (path == "/admin" or path.startswith("/admin/")):
            # Prevent browser from negotiating 304 Not Modified for admin HTML/CSS/JS.
            # Starlette's StaticFiles supports ETag/Last-Modified, so browsers may cache aggressively.
            hdrs = list(request.scope.get("headers") or [])
            hdrs = [
                (k, v)
                for (k, v) in hdrs
                if k.lower() not in (b"if-none-match", b"if-modified-since")
            ]
            request.scope["headers"] = hdrs
    except Exception:
        pass

    response = await call_next(request)
    try:
        path = request.url.path or ""
        if request.method == "GET" and (path == "/admin" or path.startswith("/admin/")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            response.headers.pop("ETag", None)
            response.headers.pop("Last-Modified", None)
    except Exception:
        pass
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(addresses_router)
app.include_router(api_customer_router)
app.include_router(api_events_router)
app.include_router(api_admin_router)
app.include_router(admin_analytics_router)
app.include_router(api_auth_router)
app.include_router(api_config_router)


_FRONTEND_ROOT = _PROJECT_ROOT / "frontend"
_SHOP_DIR = (_FRONTEND_ROOT / "shop") if (_FRONTEND_ROOT / "shop").exists() else (_FRONTEND_ROOT / "customer")
_ADMIN_DIR = _FRONTEND_ROOT / "admin"
_BI_DIR = _FRONTEND_ROOT / "bi"
_ASSETS_DIR = _FRONTEND_ROOT / "assets"
_STATIC_ROOT = _PROJECT_ROOT / "static"

if _ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")

_STATIC_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(_STATIC_ROOT)), name="static")

if _SHOP_DIR.exists():
    app.mount("/shop", StaticFiles(directory=str(_SHOP_DIR), html=True), name="shop")

if _ADMIN_DIR.exists():
    app.mount("/admin", StaticFiles(directory=str(_ADMIN_DIR), html=True), name="admin")

if _BI_DIR.exists():
    app.mount("/bi", StaticFiles(directory=str(_BI_DIR), html=True), name="bi")


@app.get("/")
def home():
    if _SHOP_DIR.exists():
        return RedirectResponse(url="/shop/")
    return {"status": "ok", "message": "Frontend not found. Create frontend/customer and frontend/admin and open /docs for API."}


@app.get("/shop")
def shop_home():
    return RedirectResponse(url="/shop/")


@app.get("/admin")
def admin_home():
    return RedirectResponse(url="/admin/")


@app.get("/bi")
def bi_home():
    return RedirectResponse(url="/bi/")
