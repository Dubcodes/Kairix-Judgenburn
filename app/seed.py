from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Competitor,
    CompetitorVehicleAssignment,
    CriteriaSet,
    Criterion,
    CurrentEventState,
    Event,
    EventSettings,
    GraphicsState,
    Judge,
    Pad,
    PinAccount,
    Run,
    RunTimer,
    Vehicle,
)


def seed_initial_data(db: Session, include_sample_competitors: bool = False) -> None:
    existing = db.scalar(select(Event).where(Event.active.is_(True)))
    if existing:
        event = existing
    else:
        event = Event(name="Burnout Competition", venue="Local Venue", event_date=None, active=True)
        db.add(event)
        db.flush()

    pad = db.scalar(select(Pad).where(Pad.event_id == event.id).limit(1))
    if not pad:
        pad = Pad(event_id=event.id, name="Pad 1")
        db.add(pad)
        db.flush()

    if not db.scalar(select(EventSettings).where(EventSettings.event_id == event.id)):
        db.add(EventSettings(event_id=event.id))

    if not db.scalar(select(CurrentEventState).where(CurrentEventState.event_id == event.id)):
        db.add(CurrentEventState(event_id=event.id, pad_id=pad.id))

    if not db.scalar(select(GraphicsState).where(GraphicsState.event_id == event.id)):
        db.add(
            GraphicsState(
                event_id=event.id,
                pad_id=pad.id,
                preset="standard_run",
                enabled_layers=["current_competitor", "judge_likeness"],
                layout_config={
                    "lower": {"x": 56, "y": 760, "w": 760, "anchor": "bottom-left", "animation": "slide-up"},
                    "delay": {"x": 480, "y": 38, "w": 960, "anchor": "top-center", "animation": "fade"},
                    "meter": {"x": 1444, "y": 790, "w": 420, "anchor": "bottom-right", "animation": "slide-up"},
                    "manual": {"x": 360, "y": 410, "w": 1200, "anchor": "center", "animation": "pop"},
                    "upnext": {"x": 1330, "y": 190, "w": 500, "anchor": "top-right", "animation": "slide-left"},
                },
            )
        )

    if not db.scalar(select(RunTimer).where(RunTimer.event_id == event.id, RunTimer.pad_id == pad.id).limit(1)):
        db.add(RunTimer(event_id=event.id, pad_id=pad.id, mode="count_up", target_seconds=90, status="ready"))

    criteria_set = db.scalar(
        select(CriteriaSet).where(CriteriaSet.event_id == event.id, CriteriaSet.active.is_(True)).limit(1)
    )
    if not criteria_set:
        criteria_set = CriteriaSet(event_id=event.id, name="Default Burnout Criteria", active=True)
        db.add(criteria_set)
        db.flush()

    defaults = [
        ("Instant Smoke", "Smoke", "numeric_score", 0, 10, 1, 1, 10),
        ("Smoke Volume", "Volume", "numeric_score", 0, 10, 1, 1, 20),
        ("Consistent Smoke", "Consistent", "numeric_score", 0, 10, 1, 1, 30),
        ("Pad Use", "Pad", "numeric_score", 0, 30, 1, 1, 40),
        ("Driver Skill", "Skill", "numeric_score", 0, 20, 1, 1, 50),
        ("Wall Taps", "Taps", "count_penalty", 0, 20, 1, 10, 60),
        ("Tyre Burst", "Tyres", "count_bonus", 0, 8, 1, 5, 70),
        ("Reverse", "Reverse", "toggle", 0, 1, 1, -5, 80),
        ("Drive off unassisted", "Drive Off", "toggle", 0, 1, 1, 10, 90),
    ]
    existing_criteria = {
        item.name
        for item in db.scalars(select(Criterion).where(Criterion.criteria_set_id == criteria_set.id)).all()
    }
    for name, short, type_, min_v, max_v, step, points, order in defaults:
        if name not in existing_criteria:
            db.add(
                Criterion(
                    criteria_set_id=criteria_set.id,
                    name=name,
                    short_label=short,
                    type=type_,
                    min_value=min_v,
                    max_value=max_v,
                    step_size=step,
                    points_per_unit=points,
                    required=False,
                    display_order=order,
                    active=True,
                )
            )

    accounts = [
        ("Judge 1", "101", "judge", 1),
        ("Judge 2", "102", "judge", 1),
        ("Graphics", "0201", "graphics", 2),
        ("Admin", "1234", "admin", 2),
        ("High Admin", "12345", "high_admin", 3),
        ("Owner", "123456", "owner", 4),
    ]
    for display_name, pin, role, level in accounts:
        account = db.scalar(select(PinAccount).where(PinAccount.event_id == event.id, PinAccount.pin == pin))
        if not account:
            account = PinAccount(
                event_id=event.id,
                display_name=display_name,
                pin=pin,
                role=role,
                permission_level=level,
                active=True,
            )
            db.add(account)
            db.flush()
        if role == "judge" and not db.scalar(select(Judge).where(Judge.pin_account_id == account.id)):
            db.add(Judge(event_id=event.id, pin_account_id=account.id, name=display_name))

    if not include_sample_competitors or db.scalar(select(Competitor).where(Competitor.event_id == event.id).limit(1)):
        db.commit()
        return

    sample_competitors = [
        ("42", "John Smith", "VK Commodore", "LS Turbo", "ABC123"),
        ("43", "Sarah Brown", "RX7", "13B Turbo", "RX7000"),
        ("44", "Mike Jones", "Falcon", "Barra", "FAL44"),
    ]
    for idx, (entry, driver, car, engine, plate) in enumerate(sample_competitors, start=1):
        competitor = Competitor(event_id=event.id, entry_number=entry, driver_name=driver, class_name="Open")
        db.add(competitor)
        db.flush()
        vehicle = Vehicle(event_id=event.id, name=car, engine=engine, plate=plate)
        db.add(vehicle)
        db.flush()
        run = Run(
            event_id=event.id,
            pad_id=pad.id,
            competitor_id=competitor.id,
            vehicle_id=vehicle.id,
            run_number=1,
            run_type="competition",
            state="queued",
            queue_position=idx,
        )
        db.add(run)
        db.flush()
        db.add(
            CompetitorVehicleAssignment(
                event_id=event.id,
                competitor_id=competitor.id,
                vehicle_id=vehicle.id,
                run_id=run.id,
            )
        )
        if idx == 1:
            state = db.scalar(select(CurrentEventState).where(CurrentEventState.event_id == event.id))
            if state:
                state.official_current_run_id = run.id
                run.state = "current"

    db.commit()
