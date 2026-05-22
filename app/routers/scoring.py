from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Criterion,
    CurrentEventState,
    JudgeSession,
    JudgeIssueReport,
    Run,
    ScoreChangeRequest,
    ScoreEntry,
    ScoreItemEntry,
    now_utc,
)
from app.schemas import ChangeRequestInput, IssueReportRequest, ScoreDraftRequest
from app.services.audit import log_action
from app.services.scoring import calculate_points

router = APIRouter(prefix="/api/scoring", tags=["scoring"])


def get_session(db: Session, session_id: int) -> JudgeSession:
    session = db.get(JudgeSession, session_id)
    if not session or not session.active:
        raise HTTPException(status_code=401, detail="Invalid session")
    session.last_seen_at = now_utc()
    return session


@router.post("/draft")
def save_score(payload: ScoreDraftRequest, db: Session = Depends(get_db)) -> dict:
    session = get_session(db, payload.session_id)
    if session.role != "judge" or not session.judge_id:
        raise HTTPException(status_code=403, detail="Judge session required")

    run = db.get(Run, payload.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.event_id != session.event_id:
        raise HTTPException(status_code=404, detail="Run not found")

    submitted_entry = db.scalar(
        select(ScoreEntry)
        .where(
            ScoreEntry.run_id == payload.run_id,
            ScoreEntry.judge_id == session.judge_id,
            ScoreEntry.source_type == "judge_submission",
            ScoreEntry.status == "submitted",
        )
        .order_by(ScoreEntry.submitted_at.desc())
    )
    if submitted_entry:
        if payload.status == "submitted":
            return {
                "ok": True,
                "score_entry_id": submitted_entry.id,
                "status": submitted_entry.status,
                "already_submitted": True,
                "missing_criteria": [],
                "total": float(submitted_entry.total or 0),
            }
        raise HTTPException(status_code=409, detail="Score already submitted for this run")

    entry = db.scalar(
        select(ScoreEntry).where(
            ScoreEntry.run_id == payload.run_id,
            ScoreEntry.judge_id == session.judge_id,
            ScoreEntry.device_id == payload.device_id,
            ScoreEntry.source_type == "judge_submission",
            ScoreEntry.status == "draft",
        )
    )
    if not entry:
        entry = ScoreEntry(
            event_id=session.event_id,
            pad_id=run.pad_id,
            run_id=run.id,
            competitor_id=run.competitor_id,
            judge_id=session.judge_id,
            device_id=payload.device_id,
            source_type="judge_submission",
            status="draft",
        )
        db.add(entry)
        db.flush()

    existing_items = {item.criterion_id: item for item in entry.items}
    total = 0.0
    missing = []
    for item_input in payload.items:
        criterion = db.get(Criterion, item_input.criterion_id)
        if not criterion:
            continue
        points = calculate_points(criterion, item_input.value)
        if points is not None:
            total += points
        else:
            missing.append(item_input.criterion_id)

        item = existing_items.get(item_input.criterion_id)
        if item:
            item.value = item_input.value
            item.calculated_points = points
            item.intentionally_blank = item_input.intentionally_blank
        else:
            db.add(
                ScoreItemEntry(
                    score_entry_id=entry.id,
                    criterion_id=item_input.criterion_id,
                    value=item_input.value,
                    calculated_points=points,
                    intentionally_blank=item_input.intentionally_blank,
                )
            )

    if payload.status == "submitted":
        entry.status = "submitted"
        entry.submitted_at = now_utc()
    entry.total = total

    log_action(
        db,
        event_id=session.event_id,
        actor_pin_account_id=session.pin_account_id,
        judge_id=session.judge_id,
        device_id=payload.device_id,
        action_type="judge_score_submitted" if payload.status == "submitted" else "judge_score_draft_saved",
        entity_type="score_entry",
        entity_id=entry.id,
        details={"run_id": run.id, "missing_criteria": missing, "total": total},
    )
    db.commit()
    return {"ok": True, "score_entry_id": entry.id, "status": entry.status, "missing_criteria": missing, "total": total}


@router.get("/my-submissions")
def my_submissions(session_id: int, db: Session = Depends(get_db)) -> dict:
    session = get_session(db, session_id)
    if session.role != "judge" or not session.judge_id:
        raise HTTPException(status_code=403, detail="Judge session required")

    entries = db.scalars(
        select(ScoreEntry)
        .where(
            ScoreEntry.event_id == session.event_id,
            ScoreEntry.judge_id == session.judge_id,
            ScoreEntry.source_type == "judge_submission",
            ScoreEntry.status == "submitted",
        )
        .order_by(ScoreEntry.submitted_at.desc())
    ).all()
    return {
        "submitted_run_ids": [entry.run_id for entry in entries],
        "submissions": [
            {
                "run_id": entry.run_id,
                "score_entry_id": entry.id,
                "total": float(entry.total or 0),
                "submitted_at": entry.submitted_at.isoformat() if entry.submitted_at else None,
            }
            for entry in entries
        ],
    }


@router.post("/issue-report")
def create_issue_report(payload: IssueReportRequest, db: Session = Depends(get_db)) -> dict:
    session = get_session(db, payload.session_id)
    if session.role != "judge" or not session.judge_id:
        raise HTTPException(status_code=403, detail="Judge session required")

    run = db.get(Run, payload.run_id) if payload.run_id else None
    if run and run.event_id != session.event_id:
        raise HTTPException(status_code=404, detail="Run not found")
    report = JudgeIssueReport(
        event_id=session.event_id,
        pad_id=run.pad_id if run else 1,
        run_id=run.id if run else None,
        judge_id=session.judge_id,
        device_id=payload.device_id,
        issue_type=payload.issue_type,
        note=payload.note,
    )
    db.add(report)
    db.flush()
    log_action(
        db,
        event_id=session.event_id,
        actor_pin_account_id=session.pin_account_id,
        judge_id=session.judge_id,
        device_id=payload.device_id,
        action_type="judge_issue_report_created",
        entity_type="judge_issue_report",
        entity_id=report.id,
        details={"issue_type": payload.issue_type, "run_id": payload.run_id},
    )
    db.commit()
    return {"ok": True, "report_id": report.id}


@router.post("/change-request")
def create_change_request(payload: ChangeRequestInput, db: Session = Depends(get_db)) -> dict:
    session = get_session(db, payload.session_id)
    if session.role != "judge" or not session.judge_id:
        raise HTTPException(status_code=403, detail="Judge session required")

    run = db.get(Run, payload.run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.event_id != session.event_id:
        raise HTTPException(status_code=404, detail="Run not found")
    state = db.scalar(select(CurrentEventState).where(CurrentEventState.event_id == session.event_id))
    original = db.scalar(
        select(ScoreEntry)
        .where(
            ScoreEntry.run_id == run.id,
            ScoreEntry.judge_id == session.judge_id,
            ScoreEntry.source_type == "judge_submission",
            ScoreEntry.status == "submitted",
        )
        .order_by(ScoreEntry.submitted_at.desc())
    )
    change_request = ScoreChangeRequest(
        event_id=session.event_id,
        pad_id=run.pad_id,
        run_id=run.id,
        competitor_id=run.competitor_id,
        judge_id=session.judge_id,
        device_id=payload.device_id,
        current_run_id_at_request=state.official_current_run_id if state else None,
        original_score_entry_id=original.id if original else None,
        requested_changes=payload.requested_changes,
        reason=payload.reason,
    )
    db.add(change_request)
    db.flush()
    log_action(
        db,
        event_id=session.event_id,
        actor_pin_account_id=session.pin_account_id,
        judge_id=session.judge_id,
        device_id=payload.device_id,
        action_type="score_change_request_created",
        entity_type="score_change_request",
        entity_id=change_request.id,
        details={"run_id": run.id},
    )
    db.commit()
    return {"ok": True, "request_id": change_request.id}
