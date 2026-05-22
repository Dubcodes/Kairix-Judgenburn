from __future__ import annotations

import json
import os
import threading
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditLog,
    Competitor,
    CompetitorVehicleAssignment,
    Conflict,
    Criterion,
    CriteriaSet,
    CurrentEventState,
    Delay,
    Event,
    EventSettings,
    GraphicsAction,
    GraphicsState,
    Judge,
    JudgeIssueReport,
    JudgeSession,
    Pad,
    PinAccount,
    RecoveryImport,
    Run,
    RunTimer,
    ScoreChangeRequest,
    ScoreEntry,
    ScoreItemEntry,
    Vehicle,
    now_utc,
)

BACKUP_MODELS = [
    Event,
    Pad,
    EventSettings,
    CriteriaSet,
    Criterion,
    PinAccount,
    Judge,
    JudgeSession,
    Competitor,
    Vehicle,
    Run,
    CompetitorVehicleAssignment,
    ScoreEntry,
    ScoreItemEntry,
    ScoreChangeRequest,
    Delay,
    CurrentEventState,
    JudgeIssueReport,
    GraphicsState,
    GraphicsAction,
    RunTimer,
    RecoveryImport,
    Conflict,
    AuditLog,
]

BACKUP_TABLES = {model.__tablename__: model for model in BACKUP_MODELS}

_scheduler_started = False


def backup_dir() -> Path:
    return Path(os.getenv("BACKUP_DIR", "/app/backups"))


def backup_interval_minutes() -> int:
    try:
        return max(0, int(os.getenv("AUTO_BACKUP_INTERVAL_MINUTES", "30")))
    except ValueError:
        return 30


def backup_retention_count() -> int:
    try:
        return max(1, int(os.getenv("AUTO_BACKUP_RETENTION_COUNT", "48")))
    except ValueError:
        return 48


def json_value(value):
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {str(key): json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_value(item) for item in value]
    return value


def rows_for_model(db: Session, model) -> list[dict]:
    output = []
    for obj in db.scalars(select(model)).all():
        output.append({col.name: json_value(getattr(obj, col.name)) for col in model.__table__.columns})
    return output


def build_backup_payload(db: Session, reason: str = "manual") -> dict:
    return {
        "generated_at": now_utc().isoformat(),
        "schema": "kairix_backup_v1",
        "reason": reason,
        "tables": {model.__tablename__: rows_for_model(db, model) for model in BACKUP_MODELS},
    }


def prune_backups(directory: Path) -> None:
    files = sorted(directory.glob("kairix-*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for old_file in files[backup_retention_count():]:
        old_file.unlink(missing_ok=True)


def write_backup(db: Session, reason: str = "scheduled") -> Path:
    directory = backup_dir()
    directory.mkdir(parents=True, exist_ok=True)
    timestamp = now_utc().strftime("%Y%m%d-%H%M%S")
    destination = directory / f"kairix-{reason}-{timestamp}.json"
    temp_file = destination.with_suffix(".tmp")
    payload = build_backup_payload(db, reason=reason)
    temp_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temp_file.replace(destination)
    prune_backups(directory)
    return destination


def backup_health() -> dict:
    directory = backup_dir()
    interval = backup_interval_minutes()
    files = sorted(directory.glob("kairix-*.json"), key=lambda item: item.stat().st_mtime, reverse=True) if directory.exists() else []
    latest = files[0] if files else None
    now = time.time()
    if not latest:
        status = "missing"
        age_seconds = None
    else:
        age_seconds = int(now - latest.stat().st_mtime)
        stale_after = max(10, interval * 60 * 2)
        status = "ok" if age_seconds <= stale_after else "stale"
    return {
        "ok": status == "ok",
        "status": status,
        "backup_dir": str(directory),
        "interval_minutes": interval,
        "retention_count": backup_retention_count(),
        "backup_count": len(files),
        "latest_file": latest.name if latest else None,
        "latest_path": str(latest) if latest else None,
        "latest_size_bytes": latest.stat().st_size if latest else None,
        "latest_age_seconds": age_seconds,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def start_backup_scheduler(session_factory: Callable[[], Session]) -> None:
    global _scheduler_started
    if _scheduler_started:
        return
    interval = backup_interval_minutes()
    if interval <= 0:
        return
    _scheduler_started = True

    def worker() -> None:
        while True:
            try:
                with session_factory() as db:
                    write_backup(db, reason="auto")
            except Exception:
                # Backup health will show stale/missing if scheduled writes fail.
                pass
            time.sleep(interval * 60)

    thread = threading.Thread(target=worker, name="kairix-auto-backup", daemon=True)
    thread.start()
