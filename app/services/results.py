from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import CriteriaSet, Criterion, Run, ScoreEntry


RESULT_MODE_LABELS = {
    "total_of_all_runs": "All heats",
    "best_1_heat": "Best 1 heat",
    "best_2_heats": "Best 2 heats",
    "best_3_heats": "Best 3 heats",
}

SCORE_AGGREGATION_LABELS = {
    "sum_all_judges": "Add all judge totals",
    "average_judge_score": "Average judge totals",
    "normalized_100": "Normalize each heat to 100",
}


def normalize_result_mode(value: str | None) -> str:
    return value if value in RESULT_MODE_LABELS else "total_of_all_runs"


def normalize_score_aggregation_mode(value: str | None) -> str:
    return value if value in SCORE_AGGREGATION_LABELS else "sum_all_judges"


def result_mode_label(value: str | None) -> str:
    return RESULT_MODE_LABELS[normalize_result_mode(value)]


def score_aggregation_label(value: str | None) -> str:
    return SCORE_AGGREGATION_LABELS[normalize_score_aggregation_mode(value)]


def best_heat_count(value: str | None) -> int | None:
    mode = normalize_result_mode(value)
    if mode.startswith("best_") and mode.endswith("_heat"):
        return int(mode.split("_")[1])
    if mode.startswith("best_") and mode.endswith("_heats"):
        return int(mode.split("_")[1])
    return None


def score_value(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value), 2)


def criterion_max_points(criterion: Criterion) -> float:
    points = float(criterion.points_per_unit or 0)
    max_value = float(criterion.max_value or 0)
    if criterion.type in {"deduction", "count_penalty"}:
        return 0.0
    if criterion.type in {"checkbox", "toggle"}:
        return max(0.0, points)
    return max(0.0, max_value * points)


def max_single_judge_score(db: Session, event_id: int) -> float:
    criteria_set = db.scalar(
        select(CriteriaSet).where(CriteriaSet.event_id == event_id, CriteriaSet.active.is_(True)).limit(1)
    )
    if not criteria_set:
        return 0.0
    criteria = db.scalars(
        select(Criterion).where(Criterion.criteria_set_id == criteria_set.id, Criterion.active.is_(True))
    ).all()
    return sum(criterion_max_points(item) for item in criteria)


def competitor_scoreboard(
    db: Session,
    event_id: int,
    result_mode: str | None,
    score_aggregation_mode: str | None = None,
    limit: int | None = None,
    submitted_before: datetime | None = None,
) -> dict:
    mode = normalize_result_mode(result_mode)
    aggregation_mode = normalize_score_aggregation_mode(score_aggregation_mode)
    best_count = best_heat_count(mode)
    aggregate_expr = func.sum(ScoreEntry.total)
    if aggregation_mode in {"average_judge_score", "normalized_100"}:
        aggregate_expr = func.avg(ScoreEntry.total)
    max_score = max_single_judge_score(db, event_id) if aggregation_mode == "normalized_100" else 0.0
    score_conditions = [
        ScoreEntry.run_id == Run.id,
        ScoreEntry.event_id == event_id,
        ScoreEntry.status == "submitted",
        ScoreEntry.active_for_results.is_(True),
    ]
    if submitted_before:
        score_conditions.append(func.coalesce(ScoreEntry.submitted_at, ScoreEntry.created_at) <= submitted_before)
    rows = db.execute(
        select(
            Run,
            func.coalesce(aggregate_expr, 0).label("total"),
            func.count(ScoreEntry.id).label("score_count"),
        )
        .outerjoin(ScoreEntry, and_(*score_conditions))
        .where(Run.event_id == event_id, Run.include_in_results.is_(True))
        .group_by(Run.id)
        .order_by(Run.queue_position, Run.id)
    ).all()

    competitors: dict[int, dict] = {}
    by_run_id: dict[int, dict] = {}
    for run, raw_total, raw_score_count in rows:
        score_count = int(raw_score_count or 0)
        run_total = float(raw_total or 0) if score_count else None
        if aggregation_mode == "normalized_100" and run_total is not None and max_score > 0:
            run_total = (run_total / max_score) * 100
        by_run_id[run.id] = {
            "run_total": score_value(run_total),
            "score_count": score_count,
        }
        competitor = competitors.setdefault(
            run.competitor_id,
            {
                "competitor_id": run.competitor_id,
                "entry_number": run.competitor.entry_number,
                "driver_name": run.competitor.driver_name,
                "class_name": run.competitor.class_name,
                "vehicle_name": run.vehicle.name if run.vehicle else "",
                "run_type": run.run_type,
                "runs": [],
                "heat_scores": {},
                "score_count": 0,
                "queue_position": run.queue_position if run.queue_position is not None else 999999,
            },
        )
        competitor["queue_position"] = min(competitor["queue_position"], run.queue_position if run.queue_position is not None else 999999)
        competitor["runs"].append(run)
        competitor["score_count"] += score_count
        if score_count:
            heat_number = int(run.heat_number or 1)
            competitor["heat_scores"][heat_number] = competitor["heat_scores"].get(heat_number, 0.0) + float(run_total or 0)

    ranked = []
    by_competitor_id = {}
    for competitor in competitors.values():
        heat_scores = [
            {"heat_number": heat, "total": score_value(total)}
            for heat, total in sorted(competitor["heat_scores"].items())
        ]
        counted_scores = sorted((item["total"] for item in heat_scores if item["total"] is not None), reverse=True)
        if best_count is not None:
            counted_scores = counted_scores[:best_count]
        total = sum(float(item) for item in counted_scores)
        payload = {
            "competitor_id": competitor["competitor_id"],
            "entry_number": competitor["entry_number"],
            "driver_name": competitor["driver_name"],
            "vehicle_name": competitor["vehicle_name"],
            "class_name": competitor["class_name"],
            "run_type": competitor["run_type"],
            "heat_scores": heat_scores,
            "counted_heat_count": len(counted_scores),
            "score_count": competitor["score_count"],
            "total": score_value(total) if competitor["score_count"] else None,
            "queue_position": competitor["queue_position"],
            "result_mode": mode,
            "result_mode_label": result_mode_label(mode),
            "score_aggregation_mode": aggregation_mode,
            "score_aggregation_label": score_aggregation_label(aggregation_mode),
        }
        ranked.append(payload)
        by_competitor_id[competitor["competitor_id"]] = payload

    ranked.sort(
        key=lambda item: (
            item["total"] is None,
            -(item["total"] or 0),
            item["queue_position"],
            item["competitor_id"],
        )
    )
    scored_ranked = [item for item in ranked if item["total"] is not None]
    if limit is not None:
        scored_ranked = scored_ranked[:limit]
    for index, item in enumerate(scored_ranked, start=1):
        item["position"] = index

    return {
        "result_mode": mode,
        "result_mode_label": result_mode_label(mode),
        "score_aggregation_mode": aggregation_mode,
        "score_aggregation_label": score_aggregation_label(aggregation_mode),
        "max_single_judge_score": score_value(max_score) if max_score else None,
        "best_heat_count": best_count,
        "competitors": scored_ranked,
        "by_competitor_id": by_competitor_id,
        "by_run_id": by_run_id,
    }
