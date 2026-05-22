from decimal import Decimal

from app.models import Criterion


def calculate_points(criterion: Criterion, value: float | int | Decimal | None) -> float | None:
    if value is None:
        return None

    numeric_value = float(value)
    per_unit = float(criterion.points_per_unit or 1)

    if criterion.type in {"checkbox", "toggle"}:
        return per_unit if numeric_value else 0

    if criterion.type in {"deduction", "count_penalty"}:
        return -abs(numeric_value * per_unit)

    if criterion.type in {"positive_bonus", "count_bonus"}:
        return numeric_value * per_unit

    return numeric_value * per_unit

