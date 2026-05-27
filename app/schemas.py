from typing import Any

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    pin: str
    device_id: str


class LoginResponse(BaseModel):
    ok: bool
    role: str
    permission_level: int
    display_name: str
    session_id: int
    judge_id: int | None = None
    redirect: str


class ScoreItemInput(BaseModel):
    criterion_id: int
    value: float | None = None
    intentionally_blank: bool = False


class AdminStatusActionInput(BaseModel):
    session_id: int
    status: str
    note: str | None = None


class ScoreOverrideInput(BaseModel):
    session_id: int
    original_score_entry_id: int
    reason: str
    items: list[ScoreItemInput]


class ScoreVoidInput(BaseModel):
    session_id: int
    reason: str


class RecoveryImportInput(BaseModel):
    session_id: int
    source_device_id: str | None = None
    raw_payload: Any
    import_as_pending: bool = True


class ScoreDraftRequest(BaseModel):
    session_id: int
    run_id: int
    device_id: str
    items: list[ScoreItemInput]
    status: str = Field(default="draft", pattern="^(draft|submitted)$")


class IssueReportRequest(BaseModel):
    session_id: int
    run_id: int | None = None
    device_id: str
    issue_type: str
    note: str | None = None


class ChangeRequestInput(BaseModel):
    session_id: int
    run_id: int
    device_id: str
    reason: str
    requested_changes: dict[str, Any] | None = None


class DelayInput(BaseModel):
    session_id: int | None = None
    message: str
    estimated_minutes: int | None = None
    estimated_seconds: int | None = None
    source: str = "admin"
    official: bool = False
    priority: str = "medium"
    visibility: str = "judges,obs,queue"


class GraphicsStateInput(BaseModel):
    session_id: int | None = None
    preset: str
    enabled_layers: list[str]
    manual_message: str | None = None
    fun_detail_mode: bool = False
    show_debug_zones: bool = False
    layout_config: dict[str, Any] | None = None


class TimerControlInput(BaseModel):
    session_id: int
    run_id: int | None = None
    mode: str = "count_up"
    target_seconds: int = 90
    elapsed_seconds: int | None = None
    action: str = "set"


class PinAccountInput(BaseModel):
    session_id: int
    display_name: str
    pin: str
    role: str
    permission_level: int
    active: bool = True


class CriterionInput(BaseModel):
    session_id: int
    name: str
    short_label: str | None = None
    type: str = Field(
        default="numeric_score",
        pattern="^(numeric_score|positive_bonus|deduction|count_bonus|count_penalty|checkbox|toggle)$",
    )
    min_value: float | None = 0
    max_value: float | None = 10
    step_size: float = 1
    points_per_unit: float = 1
    allows_negative: bool = False
    required: bool = False
    visible_to_judges: bool = True
    visible_to_graphics: bool = True
    display_order: int = 100


class CompetitorInput(BaseModel):
    session_id: int
    entry_number: str
    driver_name: str
    class_name: str | None = None
    car_name: str = "Vehicle TBC"
    engine: str | None = None
    plate: str | None = None
    sponsor: str | None = None
    notes: str | None = None
    run_type: str = "competition"
    heat_number: int = 1
    queue_position: int | None = None
    run_state: str | None = None


class CompetitorImportRow(BaseModel):
    import_row: int
    entry_number: str | None = None
    driver_name: str | None = None
    class_name: str | None = None
    car_name: str | None = None
    vehicle: str | None = None
    engine: str | None = None
    plate: str | None = None
    sponsor: str | None = None
    notes: str | None = None
    run_type: str = "competition"
    heat_number: int = 1
    skip: bool = False


class CompetitorImportCommit(BaseModel):
    session_id: int
    rows: list[CompetitorImportRow]


class RunOrderItem(BaseModel):
    run_id: int
    queue_position: int


class RunOrderInput(BaseModel):
    session_id: int
    items: list[RunOrderItem]


class EventSettingsInput(BaseModel):
    session_id: int
    event_name: str
    venue: str | None = None
    event_date: str | None = None
    landing_notice: str | None = None
    queue_notice: str | None = None
    public_notice: str | None = None
    result_mode: str = "total_of_all_runs"
    score_aggregation_mode: str = "sum_all_judges"
    public_delay_seconds: int = 5
    show_public_total_scores: bool = False
    show_graphics_total_scores: bool = True
    judge_likeness_enabled: bool = True
    delay_presets: list[dict[str, Any]] = Field(default_factory=list)


class ConnectivitySettingsInput(BaseModel):
    session_id: int
    local_base_url: str | None = None
    cloud_base_url: str | None = None
    fallback_enabled: bool = False
    prefer_local: bool = True
    auto_return_to_local: bool = True
    request_timeout_ms: int = 2500
    retry_local_after_seconds: int = 20
    health_path: str = "/api/health"


class PublicDisplaySettingsInput(BaseModel):
    session_id: int
    service_url: str | None = None
    logo_url: str | None = None
    heading: str | None = None


class EventLifecycleInput(BaseModel):
    session_id: int
    event_name: str
    venue: str | None = None
    event_date: str | None = None
    copy_criteria: bool = True
    copy_pin_accounts: bool = True
    copy_graphics_layout: bool = True
    copy_notice: bool = False
