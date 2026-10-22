"""Pure Python cycle model. No Home Assistant or third-party dependencies."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from math import isfinite
from statistics import median

DAY = 86400
HOUR = 3600


def valid_number(value: object, minimum: float, maximum: float) -> float | None:
    """Reject non-finite, missing and out-of-range measurements, never clamp."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and minimum <= number <= maximum else None


@dataclass(frozen=True)
class Point:
    timestamp: float
    value: float


@dataclass
class Cycle:
    points: list[Point] = field(default_factory=list)
    known_start: bool = False
    closed: bool = False


@dataclass
class Forecast:
    days: float | None = None
    date: datetime | None = None
    rate: float | None = None
    confidence: str = "brak"
    reason: str = "Brak wiarygodnej prognozy"
    current_days: int = 0
    complete_cycles: int = 0
    historical_rate: float | None = None
    current_rate: float | None = None
    rejected_hours: int = 0
    detected_emptyings: int = 0
    current_weight: float | None = None


def split_cycles(
    points: list[Point], markers: list[float], drop: float = 15.0
) -> tuple[list[Cycle], bool, int]:
    """Confirm emptying with two low hours, at least one hour apart.

    Manual boundaries also invalidate the next full hour: an hour containing
    pumping must never supply the baseline of the next cycle.
    """
    cycles = [Cycle()]
    pending: list[Point] = []
    rejected = 0
    marker_index = 0
    markers = sorted(markers)
    for point in sorted(points, key=lambda p: p.timestamp):
        if valid_number(point.value, 0, 100) is None:
            rejected += 1
            continue
        crossed = False
        while marker_index < len(markers) and point.timestamp >= markers[marker_index]:
            marker_index += 1
            crossed = True
        if crossed:
            cycles[-1].closed = True
            cycles.append(Cycle(known_start=True))
            pending = []
        if markers and marker_index and point.timestamp < (
            (markers[marker_index - 1] // HOUR + 1) * HOUR
        ):
            continue
        active = cycles[-1]
        if not active.points:
            active.points.append(point)
            continue
        previous = active.points[-1]
        elapsed = point.timestamp - previous.timestamp
        if elapsed > 48 * HOUR:
            # A gap can hide a whole emptying. Never fit across it.
            cycles.append(Cycle())
            cycles[-1].points.append(point)
            pending = []
            continue
        baseline = median([p.value for p in active.points[-6:]])
        if point.value <= baseline - drop:
            pending.append(point)
            if len(pending) >= 2 and pending[-1].timestamp - pending[0].timestamp >= HOUR:
                active.closed = True
                cycles.append(Cycle(points=pending[:], known_start=True))
                pending = []
            continue
        if pending:
            rejected += len(pending)
            pending = []
        # Positive jumps and moderate negative steps do not change the baseline.
        allowance = max(8.0, elapsed / DAY * 25.0)
        if abs(point.value - previous.value) > allowance:
            rejected += 1
            continue
        active.points.append(point)
    if marker_index < len(markers):
        cycles[-1].closed = True
        cycles.append(Cycle(known_start=True))
        pending = []
    return cycles, bool(pending), rejected


def daily_points(points: list[Point], zone: tzinfo, now: datetime) -> list[Point]:
    """Daily medians, >=6 hourly observations spanning >=5h, local dates.

    Exclude today to avoid a partial day's changing weight. Do not use the
    civil date as x: actual midpoint timestamps also handle DST transitions.
    """
    groups: dict[object, list[Point]] = defaultdict(list)
    today = now.astimezone(zone).date()
    for point in points:
        day = datetime.fromtimestamp(point.timestamp, zone).date()
        if day < today:
            groups[day].append(point)
    result = []
    for group in groups.values():
        times = [p.timestamp for p in group]
        if len(group) >= 6 and max(times) - min(times) >= 5 * HOUR:
            result.append(Point(median(times), median(p.value for p in group)))
    return sorted(result, key=lambda p: p.timestamp)


def robust_rate(points: list[Point]) -> tuple[float | None, float]:
    """Median pairwise slopes (Theil–Sen), with a residual error measure.

    At most 120 evenly spaced days bound work for exceptionally long cycles;
    the entire cycle still influences the estimate, not a recent-day window.
    """
    if len(points) < 3 or points[-1].timestamp - points[0].timestamp < 1.9 * DAY:
        return None, float("inf")
    if len(points) > 120:
        points = [points[round(i * (len(points) - 1) / 119)] for i in range(120)]
    slopes = [
        (right.value - left.value) / ((right.timestamp - left.timestamp) / DAY)
        for i, left in enumerate(points)
        for right in points[i + 1 :]
        if right.timestamp - left.timestamp >= 0.9 * DAY
    ]
    rate = median(slopes)
    origin = points[0].timestamp
    intercept = median(p.value - rate * (p.timestamp - origin) / DAY for p in points)
    error = median(abs(p.value - intercept - rate * (p.timestamp - origin) / DAY) for p in points)
    return rate, error


def predict(
    hours: list[Point],
    markers: list[float],
    now: datetime,
    zone: tzinfo,
    level: object,
    threshold: object,
    *,
    source_valid: bool = True,
    drop: float = 15.0,
) -> Forecast:
    """Predict only with a measurable, current positive cycle."""
    out = Forecast()
    current = valid_number(level, 0, 100)
    target = valid_number(threshold, 1, 100)
    if not source_valid or current is None or target is None:
        out.reason = "Błędny, nieaktualny lub niespójny odczyt / próg"
        return out
    cycles, pending, out.rejected_hours = split_cycles(hours, markers, drop)
    active = cycles[-1]
    out.detected_emptyings = sum(c.known_start for c in cycles)
    if pending:
        out.reason = "Możliwe opróżnienie — oczekiwanie na potwierdzenie"
        return out
    if not active.points or now.timestamp() - active.points[-1].timestamp > 6 * HOUR:
        out.reason = "Brak świeżych danych bieżącego cyklu"
        return out
    latest = active.points[-1]
    if abs(current - latest.value) > 8:
        out.reason = "Skok odczytu / możliwe opróżnienie — brak wiarygodnej prognozy"
        return out
    if current >= target:
        out.days = 0.0
        out.date = now
        out.confidence = "próg osiągnięty"
        out.reason = "Próg osiągnięty — zamów odbiór"
        return out
    current_days = daily_points(active.points, zone, now)
    out.current_days = len(current_days)
    rate, error = robust_rate(current_days)
    out.current_rate = rate
    historical = []
    for cycle in cycles[:-1]:
        daily = daily_points(cycle.points, zone, now)
        typical, scatter = robust_rate(daily)
        if (
            cycle.known_start and cycle.closed and len(daily) >= 5
            and daily[-1].value - daily[0].value >= 10
            and typical is not None and 0.05 < typical <= 25 and scatter <= 2.5
        ):
            historical.append(typical)
    out.complete_cycles = len(historical)
    out.historical_rate = median(historical) if historical else None
    if rate is None:
        out.reason = "Za krótki cykl — wymagane co najmniej 3 pełne dni danych"
        return out
    if not 0.05 < rate <= 25:
        out.reason = "Brak dodatniego, mierzalnego tempa napełniania"
        return out
    if error > 2.5 or error > max(1.5, rate * 2):
        out.reason = "Niestabilny trend — brak wiarygodnej prognozy"
        return out
    # All current-cycle days define its rate; recent days catch usage changes.
    recent, recent_error = robust_rate(current_days[-7:])
    if recent is not None and recent <= 0.05:
        out.reason = "Ostatnie dni bez wzrostu — brak wiarygodnej prognozy"
        return out
    if recent is not None and abs(recent - rate) > max(0.5, rate * 0.3):
        if recent > 25 or recent_error > 2.5:
            out.reason = "Niestabilne ostatnie dni — brak wiarygodnej prognozy"
            return out
        rate = 0.8 * recent + 0.2 * rate
    typical = out.historical_rate
    weight = 1.0
    if typical is not None:
        different = abs(rate - typical) > max(0.5, typical * 0.3)
        weight = 0.9 if different else (0.8 if len(current_days) >= 7 else 0.65)
        rate = weight * rate + (1 - weight) * typical
    out.current_weight = weight
    out.rate = rate
    out.days = (target - current) / rate
    if out.days > 365:
        out.days = out.rate = None
        out.reason = "Prognoza wykracza poza wiarygodny horyzont 365 dni"
        return out
    out.date = now + timedelta(days=out.days)
    out.confidence = "wysoka" if len(current_days) >= 7 and historical and error <= 1.5 else "ograniczona"
    out.reason = "Prognoza orientacyjna" if out.confidence == "ograniczona" else "Stabilny bieżący cykl i porównanie z historią"
    return out
