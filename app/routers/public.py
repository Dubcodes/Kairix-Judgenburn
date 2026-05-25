import asyncio
import json
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Response
from fastapi.responses import StreamingResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Competitor,
    Criterion,
    CriteriaSet,
    CurrentEventState,
    Delay,
    Event,
    EventSettings,
    GraphicsState,
    Run,
    RunTimer,
    ScoreEntry,
    ScoreItemEntry,
    Vehicle,
)
from app.services.results import competitor_scoreboard, normalize_result_mode, result_mode_label

router = APIRouter(prefix="/api", tags=["public"])


DEFAULT_CONNECTIVITY = {
    "local_base_url": "",
    "cloud_base_url": "",
    "fallback_enabled": False,
    "prefer_local": True,
    "auto_return_to_local": True,
    "request_timeout_ms": 2500,
    "retry_local_after_seconds": 20,
    "health_path": "/api/health",
}

PUBLIC_SNAPSHOT_TTL_SECONDS = 1.5
PUBLIC_QUEUE_LIMIT = 60
PUBLIC_NEXT_LIMIT = 10
PUBLIC_LEADERBOARD_LIMIT = 20
_PUBLIC_SNAPSHOT_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}


def active_event(db: Session) -> Event:
    event = db.scalar(select(Event).where(Event.active.is_(True)).limit(1))
    if not event:
        raise HTTPException(status_code=503, detail="No active event configured")
    return event


def connectivity_payload(settings: EventSettings | None) -> dict:
    config = dict(DEFAULT_CONNECTIVITY)
    if settings and isinstance(settings.connectivity_config, dict):
        config.update({key: value for key, value in settings.connectivity_config.items() if key in config})
    config["request_timeout_ms"] = max(500, min(15000, int(config.get("request_timeout_ms") or 2500)))
    config["retry_local_after_seconds"] = max(5, min(600, int(config.get("retry_local_after_seconds") or 20)))
    config["health_path"] = str(config.get("health_path") or "/api/health")
    return config


def run_payload(run: Run | None, scoreboard: dict | None = None) -> dict | None:
    if not run:
        return None
    run_score = (scoreboard or {}).get("by_run_id", {}).get(run.id, {})
    competitor_score = (scoreboard or {}).get("by_competitor_id", {}).get(run.competitor_id, {})
    return {
        "id": run.id,
        "run_number": run.run_number,
        "heat_number": run.heat_number,
        "run_type": run.run_type,
        "state": run.state,
        "queue_position": run.queue_position,
        "include_in_results": run.include_in_results,
        "score": {
            "run_total": run_score.get("run_total"),
            "run_score_count": run_score.get("score_count", 0),
            "competitor_total": competitor_score.get("total"),
            "competitor_score_count": competitor_score.get("score_count", 0),
            "counted_heat_count": competitor_score.get("counted_heat_count", 0),
            "result_mode": (scoreboard or {}).get("result_mode"),
            "result_mode_label": (scoreboard or {}).get("result_mode_label"),
        },
        "competitor": {
            "id": run.competitor.id,
            "entry_number": run.competitor.entry_number,
            "driver_name": run.competitor.driver_name,
            "class_name": run.competitor.class_name,
            "status": run.competitor.status,
        },
        "vehicle": {
            "id": run.vehicle.id,
            "name": run.vehicle.name,
            "model": run.vehicle.model,
            "engine": run.vehicle.engine,
            "plate": run.vehicle.plate,
            "sponsor": run.vehicle.sponsor,
        }
        if run.vehicle
        else None,
    }


def public_run_key(run: Run) -> str:
    entry_number = run.competitor.entry_number if run.competitor else "unknown"
    queue = run.queue_position if run.queue_position is not None else "x"
    return f"h{run.heat_number or 1}-r{run.run_number or 1}-q{queue}-e{entry_number}"


def public_score_payload(run: Run, scoreboard: dict | None, include_scores: bool) -> dict | None:
    if not include_scores:
        return None
    run_score = (scoreboard or {}).get("by_run_id", {}).get(run.id, {})
    competitor_score = (scoreboard or {}).get("by_competitor_id", {}).get(run.competitor_id, {})
    return {
        "run_total": run_score.get("run_total"),
        "run_score_count": run_score.get("score_count", 0),
        "competitor_total": competitor_score.get("total"),
        "competitor_score_count": competitor_score.get("score_count", 0),
        "counted_heat_count": competitor_score.get("counted_heat_count", 0),
        "result_mode": (scoreboard or {}).get("result_mode"),
        "result_mode_label": (scoreboard or {}).get("result_mode_label"),
    }


def public_run_payload(
    run: Run | None,
    scoreboard: dict | None = None,
    include_scores: bool = False,
    cars_away: int | None = None,
) -> dict | None:
    if not run:
        return None
    payload = {
        "key": public_run_key(run),
        "run_number": run.run_number,
        "heat_number": run.heat_number,
        "run_type": run.run_type,
        "state": run.state,
        "queue_position": run.queue_position,
        "cars_away": cars_away,
        "competitor": {
            "entry_number": run.competitor.entry_number,
            "driver_name": run.competitor.driver_name,
            "class_name": run.competitor.class_name,
        },
        "vehicle": {
            "name": run.vehicle.name if run.vehicle else "Vehicle TBC",
            "model": run.vehicle.model if run.vehicle else None,
        },
    }
    score = public_score_payload(run, scoreboard, include_scores)
    if score:
        payload["score"] = score
    return payload


def queue_sort_key(run: Run) -> tuple[int, int]:
    return (run.queue_position if run.queue_position is not None else 999999, run.id)


def active_queue_runs(db: Session, event_id: int) -> list[Run]:
    runs = db.scalars(select(Run).where(Run.event_id == event_id).order_by(Run.queue_position, Run.id)).all()
    inactive = {"finished", "skipped", "withdrawn", "disqualified"}
    return [run for run in runs if (run.state or "") not in inactive]


def actual_up_next_run(db: Session, event_id: int, current_run: Run | None) -> Run | None:
    runs = active_queue_runs(db, event_id)
    if not runs:
        return None
    if not current_run:
        return runs[0]
    current_key = queue_sort_key(current_run)
    for run in runs:
        if run.id != current_run.id and queue_sort_key(run) > current_key:
            return run
    return None


def delay_payload(delay: Delay | None) -> dict | None:
    if not delay or not delay.active:
        return None
    text = None
    remaining = None
    if delay.estimated_minutes is not None or delay.estimated_seconds is not None:
        estimated = int(delay.estimated_seconds or ((delay.estimated_minutes or 0) * 60))
        elapsed = int((datetime.now(timezone.utc) - delay.created_at).total_seconds())
        remaining = max(estimated - elapsed, 0)
        text = f"{math.ceil(remaining / 60)} min remaining" if remaining >= 60 else "Back soon"
    return {
        "id": delay.id,
        "message": delay.message,
        "estimated_minutes": delay.estimated_minutes,
        "estimated_seconds": delay.estimated_seconds,
        "countdown_text": text,
        "remaining_seconds": remaining if text else None,
        "remaining_minutes": math.ceil(remaining / 60) if text and remaining >= 60 else None,
        "source": delay.source,
        "official": delay.official,
        "priority": delay.priority,
    }


def public_delay_payload(delay: Delay | None) -> dict | None:
    payload = delay_payload(delay)
    if not payload:
        return None
    return {
        "message": payload.get("message"),
        "countdown_text": payload.get("countdown_text"),
        "remaining_seconds": payload.get("remaining_seconds"),
        "remaining_minutes": payload.get("remaining_minutes"),
    }


def timer_payload(timer: RunTimer | None) -> dict | None:
    if not timer:
        return None
    now = datetime.now(timezone.utc)
    elapsed_ms = int((timer.elapsed_offset_seconds or 0) * 1000)
    if timer.status == "running" and timer.started_at:
        elapsed_ms += max(0, int((now - timer.started_at).total_seconds() * 1000))
    elapsed = int(elapsed_ms / 1000)
    target = int(timer.target_seconds or 0)
    target_ms = target * 1000
    remaining_ms = target_ms - elapsed_ms
    remaining = int(remaining_ms / 1000)
    display_ms = remaining_ms if timer.mode == "count_down" else elapsed_ms
    display_seconds = int(display_ms / 1000)
    return {
        "id": timer.id,
        "run_id": timer.run_id,
        "mode": timer.mode,
        "status": timer.status,
        "target_seconds": target,
        "target_ms": target_ms,
        "elapsed_seconds": elapsed,
        "elapsed_ms": elapsed_ms,
        "remaining_seconds": remaining,
        "remaining_ms": remaining_ms,
        "display_seconds": display_seconds,
        "display_ms": display_ms,
        "over_seconds": max(elapsed - target, 0) if target else 0,
        "over_ms": max(elapsed_ms - target_ms, 0) if target else 0,
        "server_time_ms": int(now.timestamp() * 1000),
        "started_at_ms": int(timer.started_at.timestamp() * 1000) if timer.started_at else None,
    }


def public_timer_payload(timer: RunTimer | None) -> dict | None:
    payload = timer_payload(timer)
    if not payload:
        return None
    return {
        "mode": payload.get("mode"),
        "status": payload.get("status"),
        "target_seconds": payload.get("target_seconds"),
        "target_ms": payload.get("target_ms"),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "elapsed_ms": payload.get("elapsed_ms"),
        "remaining_seconds": payload.get("remaining_seconds"),
        "remaining_ms": payload.get("remaining_ms"),
        "display_seconds": payload.get("display_seconds"),
        "display_ms": payload.get("display_ms"),
        "over_seconds": payload.get("over_seconds"),
        "over_ms": payload.get("over_ms"),
        "server_time_ms": payload.get("server_time_ms"),
        "started_at_ms": payload.get("started_at_ms"),
    }


def leaderboard_rows(db: Session, event_id: int, result_mode: str | None) -> list[dict]:
    scoreboard = competitor_scoreboard(db, event_id, result_mode, limit=12)
    return [
        {
            "position": row.get("position"),
            "competitor_id": row.get("competitor_id"),
            "entry_number": row.get("entry_number"),
            "driver_name": row.get("driver_name"),
            "vehicle_name": row.get("vehicle_name"),
            "class_name": row.get("class_name"),
            "run_type": row.get("run_type"),
            "heat_scores": row.get("heat_scores", []),
            "counted_heat_count": row.get("counted_heat_count", 0),
            "total": row.get("total"),
            "score_count": row.get("score_count", 0),
            "result_mode": row.get("result_mode"),
            "result_mode_label": row.get("result_mode_label"),
        }
        for row in scoreboard["competitors"]
    ]


def public_leaderboard_rows(scoreboard: dict | None, include_scores: bool) -> list[dict]:
    if not include_scores or not scoreboard:
        return []
    return [
        {
            "position": row.get("position"),
            "entry_number": row.get("entry_number"),
            "driver_name": row.get("driver_name"),
            "vehicle_name": row.get("vehicle_name"),
            "class_name": row.get("class_name"),
            "run_type": row.get("run_type"),
            "heat_scores": row.get("heat_scores", []),
            "counted_heat_count": row.get("counted_heat_count", 0),
            "total": row.get("total"),
            "score_count": row.get("score_count", 0),
            "result_mode": row.get("result_mode"),
            "result_mode_label": row.get("result_mode_label"),
        }
        for row in (scoreboard.get("competitors") or [])[:PUBLIC_LEADERBOARD_LIMIT]
    ]


def public_snapshot_payload(db: Session) -> dict:
    event = active_event(db)
    state = db.scalar(select(CurrentEventState).where(CurrentEventState.event_id == event.id))
    settings = db.scalar(select(EventSettings).where(EventSettings.event_id == event.id))
    result_mode = normalize_result_mode(settings.result_mode if settings else None)
    show_public_scores = bool(settings.show_public_total_scores if settings else False)
    public_delay_seconds = max(0, int((settings.public_delay_seconds if settings else 0) or 0))
    score_cutoff = datetime.now(timezone.utc) - timedelta(seconds=public_delay_seconds) if public_delay_seconds else None
    scoreboard = (
        competitor_scoreboard(db, event.id, result_mode, submitted_before=score_cutoff)
        if show_public_scores
        else None
    )
    current_run = db.get(Run, state.official_current_run_id) if state and state.official_current_run_id else None
    queue_runs = active_queue_runs(db, event.id)
    current_index = next((idx for idx, run in enumerate(queue_runs) if current_run and run.id == current_run.id), -1)

    run_order = []
    next_runs = []
    for idx, run in enumerate(queue_runs[:PUBLIC_QUEUE_LIMIT]):
        if current_run and run.id == current_run.id:
            cars_away = 0
        elif current_index >= 0 and idx > current_index:
            cars_away = idx - current_index
        elif current_index < 0:
            cars_away = idx + 1
        else:
            cars_away = None
        public_run = public_run_payload(run, scoreboard, show_public_scores, cars_away)
        run_order.append(public_run)
        if public_run and cars_away and len(next_runs) < PUBLIC_NEXT_LIMIT:
            next_runs.append(public_run)

    official_delay = db.get(Delay, state.official_delay_id) if state and state.official_delay_id else None
    graphics_delay = db.get(Delay, state.graphics_delay_id) if state and state.graphics_delay_id else None
    delay = official_delay if official_delay and official_delay.active else graphics_delay
    timer = db.scalar(
        select(RunTimer)
        .where(RunTimer.event_id == event.id)
        .order_by(RunTimer.id.desc())
        .limit(1)
    )

    mode_label = scoreboard["result_mode_label"] if scoreboard else result_mode_label(result_mode)
    return {
        "event": {
            "name": event.name,
            "venue": event.venue,
            "event_date": event.event_date,
        },
        "settings": {
            "result_mode": result_mode,
            "result_mode_label": mode_label,
            "public_delay_seconds": public_delay_seconds,
            "show_public_total_scores": show_public_scores,
        },
        "status": {
            "current_heat": state.current_heat if state else 1,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "service": "public_snapshot",
        },
        "current_heat": state.current_heat if state else 1,
        "current_run": public_run_payload(current_run, scoreboard, show_public_scores, 0 if current_run else None),
        "next_runs": next_runs,
        "queue": run_order,
        "run_order": run_order,
        "delay": public_delay_payload(delay),
        "timer": public_timer_payload(timer),
        "leaderboard": public_leaderboard_rows(scoreboard, show_public_scores),
    }


def event_state_payload(db: Session) -> dict:
    event = active_event(db)
    state = db.scalar(select(CurrentEventState).where(CurrentEventState.event_id == event.id))
    settings = db.scalar(select(EventSettings).where(EventSettings.event_id == event.id))
    result_mode = normalize_result_mode(settings.result_mode if settings else None)
    scoreboard = competitor_scoreboard(db, event.id, result_mode)
    current_run = db.get(Run, state.official_current_run_id) if state and state.official_current_run_id else None
    featured_run = db.get(Run, state.graphics_featured_run_id) if state and state.graphics_featured_run_id else None
    up_next_run = actual_up_next_run(db, event.id, current_run)
    graphics_up_next_run = featured_run or up_next_run
    queue_runs = active_queue_runs(db, event.id)
    actual_index = next((idx for idx, run in enumerate(queue_runs) if up_next_run and run.id == up_next_run.id), -1)
    graphics_index = next((idx for idx, run in enumerate(queue_runs) if graphics_up_next_run and run.id == graphics_up_next_run.id), -1)
    if graphics_up_next_run and up_next_run and graphics_up_next_run.id == up_next_run.id:
        graphics_up_next_label = "UP NEXT"
        graphics_up_next_distance = 0
    elif graphics_index >= 0 and actual_index >= 0 and graphics_index > actual_index:
        graphics_up_next_distance = graphics_index - actual_index
        noun = "CAR" if graphics_up_next_distance == 1 else "CARS"
        graphics_up_next_label = f"{graphics_up_next_distance} {noun} AWAY"
    else:
        graphics_up_next_distance = None
        graphics_up_next_label = "FEATURED"
    official_delay = db.get(Delay, state.official_delay_id) if state and state.official_delay_id else None
    graphics_delay = db.get(Delay, state.graphics_delay_id) if state and state.graphics_delay_id else None
    graphics_state = db.scalar(select(GraphicsState).where(GraphicsState.event_id == event.id))
    timer = db.scalar(
        select(RunTimer)
        .where(RunTimer.event_id == event.id)
        .order_by(RunTimer.id.desc())
        .limit(1)
    )

    delay = official_delay if official_delay and official_delay.active else graphics_delay

    return {
        "event": {"id": event.id, "name": event.name, "venue": event.venue, "event_date": event.event_date},
        "settings": {
            "result_mode": result_mode,
            "result_mode_label": scoreboard["result_mode_label"],
            "public_delay_seconds": settings.public_delay_seconds if settings else 180,
            "show_public_total_scores": settings.show_public_total_scores if settings else False,
            "show_graphics_total_scores": settings.show_graphics_total_scores if settings else False,
            "judge_likeness_enabled": settings.judge_likeness_enabled if settings else True,
            "landing_notice": settings.landing_notice if settings else None,
            "delay_presets": settings.delay_presets if settings and isinstance(settings.delay_presets, list) else [],
            "connectivity": connectivity_payload(settings),
        },
        "current_run": run_payload(current_run, scoreboard),
        "current_heat": state.current_heat if state else 1,
        "graphics_featured_run": run_payload(featured_run, scoreboard),
        "actual_up_next_run": run_payload(up_next_run, scoreboard),
        "graphics_up_next_run": run_payload(graphics_up_next_run, scoreboard),
        "graphics_up_next_label": graphics_up_next_label,
        "graphics_up_next_distance": graphics_up_next_distance,
        "queue": [run_payload(run, scoreboard) for run in queue_runs],
        "delay": delay_payload(delay),
        "graphics": {
            "preset": graphics_state.preset,
            "enabled_layers": graphics_state.enabled_layers,
            "manual_message": graphics_state.manual_message,
            "fun_detail_mode": graphics_state.fun_detail_mode,
            "show_debug_zones": graphics_state.show_debug_zones,
            "layout_config": graphics_state.layout_config or {},
        }
        if graphics_state
        else None,
        "judge_likeness": judge_likeness(db, event.id, current_run.id if current_run else None, graphics_state),
        "leaderboard": leaderboard_rows(db, event.id, result_mode),
        "timer": timer_payload(timer),
    }


@router.get("/event-state")
def get_event_state(db: Session = Depends(get_db)) -> dict:
    return event_state_payload(db)


@router.get("/public/snapshot")
def get_public_snapshot(response: Response, db: Session = Depends(get_db)) -> dict:
    now = time.monotonic()
    cached = _PUBLIC_SNAPSHOT_CACHE.get("payload")
    if cached and now < float(_PUBLIC_SNAPSHOT_CACHE.get("expires_at") or 0):
        response.headers["Cache-Control"] = "public, max-age=1"
        return cached

    payload = public_snapshot_payload(db)
    _PUBLIC_SNAPSHOT_CACHE["payload"] = payload
    _PUBLIC_SNAPSHOT_CACHE["expires_at"] = now + PUBLIC_SNAPSHOT_TTL_SECONDS
    response.headers["Cache-Control"] = "public, max-age=1"
    return payload


@router.get("/client-config")
def get_client_config(db: Session = Depends(get_db)) -> dict:
    event = active_event(db)
    settings = db.scalar(select(EventSettings).where(EventSettings.event_id == event.id))
    return {"event_id": event.id, "connectivity": connectivity_payload(settings)}


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "kairix-judging", "checked_at": datetime.now(timezone.utc).isoformat()}


@router.get("/live/events")
async def live_events(request: Request) -> StreamingResponse:
    async def stream():
        while True:
            if await request.is_disconnected():
                break
            try:
                from app.database import SessionLocal

                with SessionLocal() as db:
                    payload = event_state_payload(db)
                payload["stream"] = {"sent_at": datetime.now(timezone.utc).isoformat()}
                data = json.dumps(payload, separators=(",", ":"), default=str)
                yield f"event: state\ndata: {data}\n\n"
            except Exception as exc:
                data = json.dumps({"ok": False, "error": str(exc)})
                yield f"event: error\ndata: {data}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/criteria")
def get_criteria(db: Session = Depends(get_db)) -> dict:
    event = active_event(db)
    criteria_set = db.scalar(
        select(CriteriaSet).where(CriteriaSet.event_id == event.id, CriteriaSet.active.is_(True)).limit(1)
    )
    if not criteria_set:
        return {"criteria_set": None, "criteria": []}
    criteria = db.scalars(
        select(Criterion)
        .where(Criterion.criteria_set_id == criteria_set.id, Criterion.active.is_(True))
        .order_by(Criterion.display_order)
    ).all()
    return {
        "criteria_set": {"id": criteria_set.id, "name": criteria_set.name},
        "criteria": [
            {
                "id": item.id,
                "name": item.name,
                "short_label": item.short_label,
                "type": item.type,
                "min_value": float(item.min_value) if item.min_value is not None else None,
                "max_value": float(item.max_value) if item.max_value is not None else None,
                "step_size": float(item.step_size),
                "points_per_unit": float(item.points_per_unit),
                "allows_negative": item.allows_negative,
                "required": item.required,
            }
            for item in criteria
        ],
    }


@router.get("/queue")
def get_queue(db: Session = Depends(get_db)) -> dict:
    event = active_event(db)
    settings = db.scalar(select(EventSettings).where(EventSettings.event_id == event.id))
    result_mode = normalize_result_mode(settings.result_mode if settings else None)
    scoreboard = competitor_scoreboard(db, event.id, result_mode)
    runs = db.scalars(
        select(Run)
        .where(
            Run.event_id == event.id,
            or_(Run.state.is_(None), Run.state.not_in(["finished", "skipped", "withdrawn"])),
        )
        .order_by(Run.queue_position, Run.id)
    ).all()
    return {
        "runs": [run_payload(run, scoreboard) for run in runs],
        "settings": {
            "result_mode": result_mode,
            "result_mode_label": scoreboard["result_mode_label"],
            "show_public_total_scores": settings.show_public_total_scores if settings else False,
        },
    }


def judge_likeness(db: Session, event_id: int, run_id: int | None, graphics_state: GraphicsState | None = None) -> dict:
    heat_config = (graphics_state.layout_config or {}).get("judge_heat", {}) if graphics_state else {}
    display_label = heat_config.get("display_label") or "Judge Heat"
    if heat_config.get("mode") == "manual":
        value = max(0, min(100, int(heat_config.get("manual_value") or 0)))
        return {"value": value, "label": display_label, "band": label_for_heat(value), "mode": "manual"}

    if not run_id:
        return {"value": 0, "label": display_label, "band": "Waiting", "mode": "live"}

    rows = db.execute(
        select(ScoreItemEntry.value)
        .join(ScoreEntry, ScoreEntry.id == ScoreItemEntry.score_entry_id)
        .join(Criterion, Criterion.id == ScoreItemEntry.criterion_id)
        .where(
            ScoreEntry.event_id == event_id,
            ScoreEntry.run_id == run_id,
            ScoreEntry.status.in_(["draft", "submitted"]),
            Criterion.visible_to_graphics.is_(True),
            Criterion.type == "numeric_score",
            ScoreItemEntry.value.is_not(None),
        )
    ).all()
    if not rows:
        return {"value": 0, "label": display_label, "band": "Waiting", "mode": "live"}

    default_max = float(heat_config.get("score_max") or 10)
    percentages = []
    for (value,) in rows:
        item_max = default_max or 10
        if item_max <= 0:
            item_max = default_max or 10
        percentages.append(max(0, min(100, (float(value) / item_max) * 100)))
    normalized = int(sum(percentages) / len(percentages))
    return {"value": normalized, "label": display_label, "band": label_for_heat(normalized), "mode": "live"}


def label_for_heat(normalized: int) -> str:
    if normalized < 20:
        return "Warming Up"
    if normalized < 45:
        return "Building"
    if normalized < 70:
        return "Strong Run"
    if normalized < 90:
        return "Wild Run"
    return "Crowd Melter"
