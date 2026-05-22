from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Event, Judge, JudgeSession, PinAccount, now_utc
from app.schemas import LoginRequest, LoginResponse
from app.services.audit import log_action

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/pin", response_model=LoginResponse)
def login_with_pin(payload: LoginRequest, response: Response, db: Session = Depends(get_db)) -> LoginResponse:
    pin = payload.pin.strip()
    active_event = db.scalar(select(Event).where(Event.active.is_(True)).limit(1))
    if not active_event:
        raise HTTPException(status_code=503, detail="No active event configured")
    account = db.scalar(
        select(PinAccount)
        .where(
            PinAccount.event_id == active_event.id,
            PinAccount.pin == pin,
            PinAccount.active.is_(True),
        )
        .limit(1)
    )

    if not account:
        log_action(
            db,
            action_type="failed_pin_login",
            device_id=payload.device_id,
            details={"pin_length": len(pin)},
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid PIN")

    judge = None
    if account.role == "judge":
        judge = db.scalar(select(Judge).where(Judge.pin_account_id == account.id, Judge.active.is_(True)))

    session = JudgeSession(
        event_id=account.event_id,
        judge_id=judge.id if judge else None,
        pin_account_id=account.id,
        device_id=payload.device_id,
        role=account.role,
        last_seen_at=now_utc(),
    )
    db.add(session)
    db.flush()

    log_action(
        db,
        event_id=account.event_id,
        actor_pin_account_id=account.id,
        judge_id=judge.id if judge else None,
        device_id=payload.device_id,
        action_type="pin_login",
        entity_type="judge_session",
        entity_id=session.id,
        details={"role": account.role},
    )
    db.commit()
    response.set_cookie(
        "kairix_session_id",
        str(session.id),
        max_age=60 * 60 * 14,
        httponly=True,
        samesite="lax",
    )
    response.set_cookie(
        "kairix_client_session_id",
        str(session.id),
        max_age=60 * 60 * 14,
        httponly=False,
        samesite="lax",
    )
    response.set_cookie(
        "kairix_client_role",
        account.role,
        max_age=60 * 60 * 14,
        httponly=False,
        samesite="lax",
    )

    redirect = "/judge"
    if account.role == "graphics":
        redirect = "/gfx-control"
    elif account.role in {"admin", "high_admin", "owner"}:
        redirect = "/admin"

    return LoginResponse(
        ok=True,
        role=account.role,
        permission_level=account.permission_level,
        display_name=account.display_name,
        session_id=session.id,
        judge_id=judge.id if judge else None,
        redirect=redirect,
    )


@router.get("/session")
def check_session(
    session_id: int | None = None,
    kairix_session_id: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if session_id is None and kairix_session_id and kairix_session_id.isdigit():
        session_id = int(kairix_session_id)
    if session_id is None:
        raise HTTPException(status_code=401, detail="Invalid session")
    session = db.get(JudgeSession, session_id)
    if not session or not session.active:
        raise HTTPException(status_code=401, detail="Invalid session")

    account = db.get(PinAccount, session.pin_account_id)
    if not account or not account.active:
        raise HTTPException(status_code=401, detail="PIN account inactive")

    session.last_seen_at = now_utc()
    db.commit()
    return {
        "ok": True,
        "role": session.role,
        "permission_level": account.permission_level,
        "display_name": account.display_name,
        "session_id": session.id,
        "judge_id": session.judge_id,
    }
