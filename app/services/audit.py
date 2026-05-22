from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog


def log_action(
    db: Session,
    *,
    action_type: str,
    event_id: int | None = None,
    actor_pin_account_id: int | None = None,
    judge_id: int | None = None,
    device_id: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            event_id=event_id,
            actor_pin_account_id=actor_pin_account_id,
            judge_id=judge_id,
            device_id=device_id,
            action_type=action_type,
            entity_type=entity_type,
            entity_id=entity_id,
            details=details,
        )
    )

