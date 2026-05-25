from fastapi import Depends, FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import Base, SessionLocal, engine, get_db
from app.models import JudgeSession, PinAccount, now_utc
from app.routers import admin, auth, public, scoring
from app.seed import seed_initial_data
from app.services.backups import start_backup_scheduler
from app.version import APP_VERSION


app = FastAPI(title="Kairix Judgenburn System", version=APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PROTECTED_STATIC_HTML = {
    "/static/admin.html",
    "/static/gfx-control.html",
    "/static/gfx-settings.html",
    "/static/judge.html",
    "/static/recovery.html",
}


@app.middleware("http")
async def block_protected_static_html(request: Request, call_next):
    if request.url.path in PROTECTED_STATIC_HTML:
        return RedirectResponse("/", status_code=303)
    return await call_next(request)


def ensure_schema_upgrades() -> None:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE graphics_state ADD COLUMN IF NOT EXISTS layout_config JSON DEFAULT '{}'"))
        conn.execute(text("ALTER TABLE delays ADD COLUMN IF NOT EXISTS estimated_seconds INTEGER"))
        conn.execute(text("ALTER TABLE runs ALTER COLUMN state DROP NOT NULL"))
        conn.execute(text("ALTER TABLE runs ADD COLUMN IF NOT EXISTS heat_number INTEGER DEFAULT 1"))
        conn.execute(text("ALTER TABLE current_event_state ADD COLUMN IF NOT EXISTS current_heat INTEGER DEFAULT 1"))
        conn.execute(text("ALTER TABLE run_timers ADD COLUMN IF NOT EXISTS source VARCHAR(60) DEFAULT 'run_control'"))
        conn.execute(text("ALTER TABLE run_timers ADD COLUMN IF NOT EXISTS notes TEXT"))
        conn.execute(text("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS landing_notice TEXT"))
        conn.execute(text("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS connectivity_config JSON DEFAULT '{}'"))
        conn.execute(text("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS show_public_total_scores BOOLEAN DEFAULT FALSE"))
        conn.execute(text("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS show_graphics_total_scores BOOLEAN DEFAULT TRUE"))
        conn.execute(text("ALTER TABLE event_settings ADD COLUMN IF NOT EXISTS delay_presets JSON DEFAULT '[]'"))


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_upgrades()
    with SessionLocal() as db:
        seed_initial_data(db, include_sample_competitors=False)
    start_backup_scheduler(SessionLocal)


app.include_router(auth.router)
app.include_router(public.router)
app.include_router(scoring.router)
app.include_router(admin.router)

app.mount("/static", StaticFiles(directory="app/static"), name="static")


def protected_page(
    request: Request,
    db: Session,
    allowed_roles: set[str],
    path: str,
):
    raw_session_id = request.cookies.get("kairix_session_id")
    if not raw_session_id or not raw_session_id.isdigit():
        return RedirectResponse("/", status_code=303)

    session = db.get(JudgeSession, int(raw_session_id))
    if not session or not session.active or session.role not in allowed_roles:
        return RedirectResponse("/", status_code=303)

    account = db.scalar(
        select(PinAccount).where(PinAccount.id == session.pin_account_id, PinAccount.active.is_(True)).limit(1)
    )
    if not account:
        return RedirectResponse("/", status_code=303)

    session.last_seen_at = now_utc()
    db.commit()
    return FileResponse(path)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse("app/static/index.html")


@app.get("/judge", include_in_schema=False)
def judge_page(request: Request, db: Session = Depends(get_db)):
    return protected_page(request, db, {"judge"}, "app/static/judge.html")


@app.get("/admin", include_in_schema=False)
def admin_page(request: Request, db: Session = Depends(get_db)):
    return protected_page(request, db, {"admin", "high_admin", "owner"}, "app/static/admin.html")


@app.get("/gfx-control", include_in_schema=False)
def gfx_control_page(request: Request, db: Session = Depends(get_db)):
    return protected_page(request, db, {"graphics", "high_admin", "owner"}, "app/static/gfx-control.html")


@app.get("/gfx-settings", include_in_schema=False)
def gfx_settings_page(request: Request, db: Session = Depends(get_db)):
    return protected_page(request, db, {"graphics", "high_admin", "owner"}, "app/static/gfx-settings.html")


@app.get("/obs-overlay", include_in_schema=False)
def obs_overlay_page() -> FileResponse:
    return FileResponse("app/static/obs-overlay.html")


@app.get("/queue", include_in_schema=False)
def queue_page() -> FileResponse:
    return FileResponse("app/static/queue.html")


@app.get("/public", include_in_schema=False)
def public_display_page() -> FileResponse:
    return FileResponse("app/static/public.html")


@app.get("/public/{view_name}", include_in_schema=False)
def public_display_view(view_name: str) -> FileResponse:
    return FileResponse("app/static/public.html")


@app.get("/recovery", include_in_schema=False)
def recovery_page(request: Request, db: Session = Depends(get_db)):
    return protected_page(request, db, {"judge", "high_admin", "owner"}, "app/static/recovery.html")
