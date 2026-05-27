from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)


class Event(TimestampMixin, Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    venue: Mapped[str | None] = mapped_column(String(160))
    event_date: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    settings: Mapped["EventSettings"] = relationship(back_populates="event", uselist=False)


class Pad(TimestampMixin, Base):
    __tablename__ = "pads"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(80), default="Pad 1")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class EventSettings(TimestampMixin, Base):
    __tablename__ = "event_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True)
    result_mode: Mapped[str] = mapped_column(String(40), default="total_of_all_runs")
    score_aggregation_mode: Mapped[str] = mapped_column(String(40), default="sum_all_judges")
    public_delay_seconds: Mapped[int] = mapped_column(Integer, default=5)
    show_public_total_scores: Mapped[bool] = mapped_column(Boolean, default=False)
    show_graphics_total_scores: Mapped[bool] = mapped_column(Boolean, default=True)
    judge_likeness_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_submit_with_nulls: Mapped[bool] = mapped_column(Boolean, default=True)
    max_judges: Mapped[int] = mapped_column(Integer, default=20)
    landing_notice: Mapped[str | None] = mapped_column(Text)
    queue_notice: Mapped[str | None] = mapped_column(Text)
    public_notice: Mapped[str | None] = mapped_column(Text)
    connectivity_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    public_display_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    delay_presets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)

    event: Mapped[Event] = relationship(back_populates="settings")


class Competitor(TimestampMixin, Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    entry_number: Mapped[str] = mapped_column(String(40))
    driver_name: Mapped[str] = mapped_column(String(160))
    class_name: Mapped[str | None] = mapped_column(String(80))
    contact_info: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="registered")

    __table_args__ = (UniqueConstraint("event_id", "entry_number", name="uq_competitor_event_entry"),)


class Vehicle(TimestampMixin, Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(160))
    engine: Mapped[str | None] = mapped_column(String(160))
    plate: Mapped[str | None] = mapped_column(String(80))
    sponsor: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)


class CompetitorVehicleAssignment(TimestampMixin, Base):
    __tablename__ = "competitor_vehicle_assignments"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    vehicle_id: Mapped[int] = mapped_column(ForeignKey("vehicles.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Run(TimestampMixin, Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.id"), nullable=True)
    run_number: Mapped[int] = mapped_column(Integer, default=1)
    heat_number: Mapped[int] = mapped_column(Integer, default=1)
    run_type: Mapped[str] = mapped_column(String(40), default="competition")
    state: Mapped[str | None] = mapped_column(String(40), nullable=True)
    queue_position: Mapped[int] = mapped_column(Integer, default=0)
    include_in_results: Mapped[bool] = mapped_column(Boolean, default=True)

    competitor: Mapped[Competitor] = relationship()
    vehicle: Mapped[Vehicle | None] = relationship()


class CurrentEventState(TimestampMixin, Base):
    __tablename__ = "current_event_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True)
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    current_heat: Mapped[int] = mapped_column(Integer, default=1)
    official_current_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    graphics_featured_run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    official_delay_id: Mapped[int | None] = mapped_column(ForeignKey("delays.id"), nullable=True)
    graphics_delay_id: Mapped[int | None] = mapped_column(ForeignKey("delays.id"), nullable=True)


class CriteriaSet(TimestampMixin, Base):
    __tablename__ = "criteria_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    name: Mapped[str] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Criterion(TimestampMixin, Base):
    __tablename__ = "criteria"

    id: Mapped[int] = mapped_column(primary_key=True)
    criteria_set_id: Mapped[int] = mapped_column(ForeignKey("criteria_sets.id"))
    name: Mapped[str] = mapped_column(String(120))
    short_label: Mapped[str | None] = mapped_column(String(40))
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(40), default="numeric_score")
    min_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    max_value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    step_size: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    points_per_unit: Mapped[float] = mapped_column(Numeric(10, 2), default=1)
    allows_negative: Mapped[bool] = mapped_column(Boolean, default=False)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_to_judges: Mapped[bool] = mapped_column(Boolean, default=True)
    visible_to_graphics: Mapped[bool] = mapped_column(Boolean, default=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class PinAccount(TimestampMixin, Base):
    __tablename__ = "pin_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    display_name: Mapped[str] = mapped_column(String(120))
    pin: Mapped[str] = mapped_column(String(12))
    role: Mapped[str] = mapped_column(String(40))
    permission_level: Mapped[int] = mapped_column(Integer, default=1)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    __table_args__ = (UniqueConstraint("event_id", "pin", name="uq_pin_event_pin"),)


class Judge(TimestampMixin, Base):
    __tablename__ = "judges"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pin_account_id: Mapped[int] = mapped_column(ForeignKey("pin_accounts.id"))
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="active")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class JudgeSession(TimestampMixin, Base):
    __tablename__ = "judge_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("judges.id"), nullable=True)
    pin_account_id: Mapped[int] = mapped_column(ForeignKey("pin_accounts.id"))
    device_id: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ScoreEntry(TimestampMixin, Base):
    __tablename__ = "score_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("judges.id"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(String(60), default="judge_submission")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_score_entry_id: Mapped[int | None] = mapped_column(ForeignKey("score_entries.id"), nullable=True)
    active_for_results: Mapped[bool] = mapped_column(Boolean, default=True)
    reason: Mapped[str | None] = mapped_column(Text)
    total: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    items: Mapped[list["ScoreItemEntry"]] = relationship(back_populates="score_entry", cascade="all, delete-orphan")


class ScoreItemEntry(TimestampMixin, Base):
    __tablename__ = "score_item_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    score_entry_id: Mapped[int] = mapped_column(ForeignKey("score_entries.id"))
    criterion_id: Mapped[int] = mapped_column(ForeignKey("criteria.id"))
    value: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    calculated_points: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    intentionally_blank: Mapped[bool] = mapped_column(Boolean, default=False)

    score_entry: Mapped[ScoreEntry] = relationship(back_populates="items")
    criterion: Mapped[Criterion] = relationship()


class ScoreChangeRequest(TimestampMixin, Base):
    __tablename__ = "score_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    judge_id: Mapped[int] = mapped_column(ForeignKey("judges.id"))
    device_id: Mapped[str | None] = mapped_column(String(120))
    current_run_id_at_request: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    original_score_entry_id: Mapped[int | None] = mapped_column(ForeignKey("score_entries.id"), nullable=True)
    requested_changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    resolved_by_pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Delay(TimestampMixin, Base):
    __tablename__ = "delays"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    created_by_pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    created_by_role: Mapped[str | None] = mapped_column(String(40))
    source: Mapped[str] = mapped_column(String(40), default="admin")
    message: Mapped[str] = mapped_column(String(240))
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    visibility: Mapped[str] = mapped_column(String(80), default="judges,obs,queue")
    official: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[str] = mapped_column(String(40), default="medium")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JudgeIssueReport(TimestampMixin, Base):
    __tablename__ = "judge_issue_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    judge_id: Mapped[int] = mapped_column(ForeignKey("judges.id"))
    device_id: Mapped[str | None] = mapped_column(String(120))
    issue_type: Mapped[str] = mapped_column(String(60))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="open")


class GraphicsState(TimestampMixin, Base):
    __tablename__ = "graphics_state"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), unique=True)
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    preset: Mapped[str] = mapped_column(String(60), default="standard_run")
    enabled_layers: Mapped[list[str]] = mapped_column(JSON, default=list)
    manual_message: Mapped[str | None] = mapped_column(String(240))
    fun_detail_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    show_debug_zones: Mapped[bool] = mapped_column(Boolean, default=False)
    layout_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class GraphicsAction(TimestampMixin, Base):
    __tablename__ = "graphics_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    action_type: Mapped[str] = mapped_column(String(80))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RunTimer(TimestampMixin, Base):
    __tablename__ = "run_timers"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    pad_id: Mapped[int] = mapped_column(ForeignKey("pads.id"), default=1)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(40), default="count_up")
    target_seconds: Mapped[int] = mapped_column(Integer, default=90)
    elapsed_offset_seconds: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="ready")
    source: Mapped[str] = mapped_column(String(60), default="run_control")
    notes: Mapped[str | None] = mapped_column(Text)


class RecoveryImport(TimestampMixin, Base):
    __tablename__ = "recovery_imports"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    imported_by_pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    source_device_id: Mapped[str | None] = mapped_column(String(120))
    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(40), default="pending_review")


class Conflict(TimestampMixin, Base):
    __tablename__ = "conflicts"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"))
    conflict_type: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(40), default="open")
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by_pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("events.id"), nullable=True)
    actor_pin_account_id: Mapped[int | None] = mapped_column(ForeignKey("pin_accounts.id"), nullable=True)
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("judges.id"), nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(120))
    action_type: Mapped[str] = mapped_column(String(100))
    entity_type: Mapped[str | None] = mapped_column(String(80))
    entity_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
