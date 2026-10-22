"""Read Recorder through HA APIs, never a SQLite path or external connection."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from math import ceil

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.history import get_significant_states
from homeassistant.components.recorder.statistics import get_metadata, statistics_during_period
from homeassistant.core import HomeAssistant

from .model import HOUR, Point, valid_number

DISTANCE_UNITS = {"m": 1.0, "cm": 0.01, "mm": 0.001}


def distance_percent(value: object, unit: str | None) -> float | None:
    """Historical fallback only; live percentage always comes from its entity."""
    scale = DISTANCE_UNITS.get(unit or "m")
    number = valid_number(value, 0, 1600)
    if scale is None or number is None:
        return None
    metres = number * scale
    return (1 - metres / 1.60) * 100 if 0 <= metres <= 1.60 else None


def aggregate_states(states: list, start: datetime, end: datetime, convert) -> dict[int, float | None]:
    """Equal-duration sampling avoids weighting chatty sensor periods more.

    Carry a value at most six hours; unknown/unavailable explicitly breaks it.
    Every hour needs three quarter-hour samples; median removes isolated noise.
    The caller uses only completed hours so incomplete hours cannot erase them.
    """
    from statistics import median

    buckets: dict[int, list[float]] = defaultdict(list)
    touched: set[int] = set()
    for index, state in enumerate(states):
        timestamp = state.last_updated.timestamp()
        until = min(
            states[index + 1].last_updated.timestamp() if index + 1 < len(states) else end.timestamp(),
            end.timestamp(), timestamp + 6 * HOUR,
        )
        tick = ceil(max(timestamp, start.timestamp()) / 900) * 900
        value = convert(state.state, state.attributes.get("unit_of_measurement"))
        while tick < until:
            hour = int(tick // HOUR * HOUR)
            touched.add(hour)
            if value is not None:
                buckets[hour].append(value)
            tick += 900
    return {
        hour: median(buckets[hour]) if len(buckets[hour]) >= 3 else None
        for hour in touched
    }


def read_history(
    hass: HomeAssistant, level_entity: str, distance_entity: str,
    start: datetime, end: datetime, initial: bool,
) -> tuple[dict[int, float | None], dict]:
    """Synchronous function: MUST run on Recorder's executor.

    Initial import covers the entire configured history, including all available
    long-term hourly means. Raw states take precedence in overlapping hours.
    """
    entities = {level_entity, distance_entity}
    metadata = get_metadata(hass, statistic_ids=entities)
    stats = statistics_during_period(hass, start, end, entities, "hour", None, {"mean", "min", "max"})
    hours: dict[int, float | None] = {}
    counts = {"level_statistics_hours": 0, "distance_statistics_hours": 0, "raw_hours": 0}
    # Distance first: the original percentage wins wherever both are available.
    for entity in (distance_entity, level_entity):
        meta = metadata.get(entity)
        if meta is None:
            continue
        unit = meta[1].get("unit_of_measurement")
        if entity == level_entity and unit != "%":
            continue
        convert = distance_percent if entity == distance_entity else lambda value, _: valid_number(value, 0, 100)
        for row in stats.get(entity, []):
            timestamp = int(row["start"])
            mean = convert(row.get("mean"), unit)
            low, high = convert(row.get("min"), unit), convert(row.get("max"), unit)
            if mean is None or low is None or high is None or abs(high - low) >= 15:
                # An hour spanning pumping / a big spike is not a baseline.
                hours[timestamp] = None
                continue
            hours[timestamp] = mean
            counts["distance_statistics_hours" if entity == distance_entity else "level_statistics_hours"] += 1
    oldest = get_instance(hass).states_manager.oldest_ts
    raw_start = max(start, datetime.fromtimestamp(oldest, timezone.utc)) if oldest else start
    # Align to a whole hour; no-attributes=False allows distance unit conversion.
    cursor = raw_start.replace(minute=0, second=0, microsecond=0)
    while cursor < end:
        chunk_end = min(cursor + timedelta(days=31), end)
        raw = get_significant_states(
            hass, cursor, chunk_end, sorted(entities),
            include_start_time_state=True, significant_changes_only=False,
            minimal_response=False, no_attributes=False,
        )
        for entity in (distance_entity, level_entity):
            convert = distance_percent if entity == distance_entity else lambda value, _: valid_number(value, 0, 100)
            aggregated = aggregate_states(raw.get(entity, []), cursor, chunk_end, convert)
            hours.update(aggregated)
            counts["raw_hours"] += sum(value is not None for value in aggregated.values())
        cursor = chunk_end
    diagnostics = {
        **counts,
        "import_start": start.isoformat(),
        "import_end": end.isoformat(),
        "initial_import": initial,
        "statistics_entities": sorted(metadata),
    }
    return hours, diagnostics


def as_points(hours: dict[int, float]) -> list[Point]:
    return [Point(float(t), v) for t, v in sorted(hours.items())]
