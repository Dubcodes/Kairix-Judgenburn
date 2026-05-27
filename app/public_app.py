import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.version import APP_VERSION


PUBLIC_UPSTREAM_URL = os.getenv("PUBLIC_UPSTREAM_URL", "").rstrip("/")
PUBLIC_PROXY_TIMEOUT_SECONDS = float(os.getenv("PUBLIC_PROXY_TIMEOUT_SECONDS", "4"))
MAX_PUBLIC_RESPONSE_BYTES = 2 * 1024 * 1024

app = FastAPI(title="Judgenburn Public Display", version=APP_VERSION)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


def upstream_json(path: str) -> JSONResponse:
    if not PUBLIC_UPSTREAM_URL:
        raise HTTPException(status_code=503, detail="PUBLIC_UPSTREAM_URL is not configured")
    url = f"{PUBLIC_UPSTREAM_URL}{path}"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "kairix-public-display"})
    try:
        with urlopen(request, timeout=PUBLIC_PROXY_TIMEOUT_SECONDS) as response:
            body = response.read(MAX_PUBLIC_RESPONSE_BYTES + 1)
            if len(body) > MAX_PUBLIC_RESPONSE_BYTES:
                raise HTTPException(status_code=502, detail="Public upstream response is too large")
            payload = json.loads(body.decode("utf-8"))
            headers = {"Cache-Control": response.headers.get("Cache-Control", "public, max-age=1")}
            return JSONResponse(payload, headers=headers)
    except HTTPError as exc:
        raise HTTPException(status_code=exc.code, detail=f"Public upstream returned {exc.code}") from exc
    except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=502, detail=f"Public upstream unavailable: {exc}") from exc


@app.get("/", include_in_schema=False)
def public_home() -> FileResponse:
    return FileResponse("app/static/public.html")


@app.get("/queue", include_in_schema=False)
def queue_page() -> FileResponse:
    return FileResponse("app/static/queue.html")


@app.get("/public", include_in_schema=False)
def public_display_page() -> FileResponse:
    return FileResponse("app/static/public.html")


@app.get("/public/{view_name}", include_in_schema=False)
def public_display_view(view_name: str) -> FileResponse:
    return FileResponse("app/static/public.html")


@app.get("/api/public/snapshot")
def public_snapshot() -> JSONResponse:
    return upstream_json("/api/public/snapshot")


@app.get("/api/health")
def public_health() -> dict:
    return {
        "ok": True,
        "service": "judgenburn-public-display",
        "upstream_configured": bool(PUBLIC_UPSTREAM_URL),
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
