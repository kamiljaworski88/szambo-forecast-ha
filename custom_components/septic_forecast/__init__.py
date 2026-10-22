"""Local, YAML-configured forecast with Recorder backfill and persisted cycles."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
import logging

import voluptuous as vol

from homeassistant.components.recorder import get_instance, is_entity_recorded
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, discovery
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DEFAULT_DISTANCE, DEFAULT_LEVEL, DEFAULT_THRESHOLD, DOMAIN, SIGNAL_UPDATE
from .history_reader import as_points, distance_percent, read_history
from .model import Forecast, predict, valid_number

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema({
    vol.Optional(DOMAIN): vol.Schema({
        vol.Optional("level_entity", default=DEFAULT_LEVEL): cv.entity_id,
        vol.Optional("distance_entity", default=DEFAULT_DISTANCE): cv.entity_id,
        vol.Optional("threshold_entity", default=DEFAULT_THRESHOLD): cv.entity_id,
        vol.Optional("history_start", default="2000-01-01"): cv.date,
        vol.Optional("emptying_drop", default=15.0): vol.All(vol.Coerce(float), vol.Range(min=10, max=50)),
    }),
}, extra=vol.ALLOW_EXTRA)


class ForecastRuntime:
    """One installation, one persistent data store, no network I/O."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        self.hass, self.config = hass, config
        self.store = Store(hass, 1, DOMAIN)
        self.hours: dict[int, float] = {}
        self.markers: list[float] = []
        self.cursor: float | None = None
        self.result = Forecast(reason="Wczytywanie historii Recorder")
        self.diagnostics: dict = {}
        self.error = False
        self.lock = asyncio.Lock()
        self._dirty = False
        self._calculation: asyncio.Task | None = None

    async def async_load(self) -> None:
        if (data := await self.store.async_load()) and data.get("sources") == self.sources:
            self.hours = {int(t): v for t, v in data.get("hours", [])}
            self.markers = data.get("manual_emptyings", [])
            self.cursor = data.get("cursor")
            self.diagnostics = data.get("diagnostics", {})

    @property
    def sources(self) -> list[str]:
        return [self.config["level_entity"], self.config["distance_entity"], str(self.config["history_start"])]

    def snapshot(self) -> dict:
        return {
            "sources": self.sources,
            "hours": sorted(self.hours.items()),
            "manual_emptyings": self.markers[:],
            "cursor": self.cursor,
            "diagnostics": self.diagnostics.copy(),
        }

    @callback
    def recalculate(self, _event=None) -> None:
        self._dirty = True
        if self._calculation is None or self._calculation.done():
            self._calculation = self.hass.async_create_task(self._async_recalculate())

    async def _async_recalculate(self) -> None:
        # Merge bursts of state changes; replaying years of cycles is CPU work
        # and must not run on HA's event loop.
        while self._dirty:
            self._dirty = False
            await self._async_calculate_once()

    async def _async_calculate_once(self) -> None:
        now = dt_util.utcnow()
        state = self.hass.states.get(self.config["level_entity"])
        distance = self.hass.states.get(self.config["distance_entity"])
        threshold = self.hass.states.get(self.config["threshold_entity"])
        valid = state is not None and distance is not None
        if valid:
            percent = valid_number(state.state, 0, 100)
            converted = distance_percent(distance.state, distance.attributes.get("unit_of_measurement"))
            valid = (
                percent is not None and converted is not None and abs(percent - converted) <= 5
                and all(0 <= (now - item.last_reported).total_seconds() <= 6 * 3600 for item in (state, distance))
            )
        if self.error:
            self.result = Forecast(reason="Błąd odczytu / zapisu historii — sprawdź dziennik HA")
        elif self.cursor is None:
            self.result = Forecast(reason="Wczytywanie historii Recorder")
        else:
            hours, markers = self.hours.copy(), self.markers[:]
            zone = dt_util.get_time_zone(self.hass.config.time_zone)
            level = state.state if state else None
            target = threshold.state if threshold else None
            drop = self.config["emptying_drop"]
            self.result = await self.hass.async_add_executor_job(
                lambda: predict(as_points(hours), markers, now, zone, level, target, source_valid=valid, drop=drop)
            )
        if not self._dirty:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_refresh(self, _now=None) -> None:
        if self.lock.locked():
            return
        async with self.lock:
            try:
                now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
                initial = self.cursor is None
                start = datetime.combine(self.config["history_start"], datetime.min.time(), timezone.utc)
                if self.cursor is not None:
                    start = max(start, datetime.fromtimestamp(self.cursor, timezone.utc) - timedelta(hours=6))
                rows, diagnostics = await get_instance(self.hass).async_add_executor_job(
                    partial(read_history, self.hass, self.config["level_entity"], self.config["distance_entity"], start, now, initial)
                )
                for timestamp, value in rows.items():
                    if value is None:
                        self.hours.pop(timestamp, None)
                    else:
                        self.hours[timestamp] = value
                if initial:
                    self.diagnostics = {"initial_import": diagnostics}
                self.diagnostics["latest_import"] = diagnostics
                self.diagnostics["archived_hours"] = len(self.hours)
                self.diagnostics["oldest_hour"] = min(self.hours) if self.hours else None
                self.diagnostics["newest_hour"] = max(self.hours) if self.hours else None
                self.diagnostics["recorded_entities"] = {
                    entity: is_entity_recorded(self.hass, entity) for entity in self.sources[:2]
                }
                self.cursor = now.timestamp()
                await self.store.async_save(self.snapshot())
                self.error = False
            except Exception:
                _LOGGER.exception("Nie udało się wczytać lub zachować historii szamba")
                self.error = True
            self.recalculate()

    async def async_mark_emptying(self, call: ServiceCall) -> None:
        """Call after pumping is complete and both source sensors have settled."""
        state = self.hass.states.get(self.config["level_entity"])
        distance = self.hass.states.get(self.config["distance_entity"])
        level = valid_number(state.state if state else None, 0, 100)
        converted = distance_percent(distance.state, distance.attributes.get("unit_of_measurement")) if distance else None
        fresh = all(
            item is not None and 0 <= (dt_util.utcnow() - item.last_reported).total_seconds() <= 6 * 3600
            for item in (state, distance)
        )
        if level is None or converted is None or abs(level - converted) > 5 or not fresh:
            raise HomeAssistantError("Poczekaj na poprawne, spójne odczyty po odbiorze szamba")
        async with self.lock:
            old_markers = self.markers[:]
            self.markers.append(dt_util.utcnow().timestamp())
            try:
                await self.store.async_save(self.snapshot())
            except Exception:
                self.markers = old_markers
                raise
            self.recalculate()


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    if DOMAIN not in config:
        return True
    runtime = ForecastRuntime(hass, config[DOMAIN])
    await runtime.async_load()
    hass.data[DOMAIN] = runtime
    await discovery.async_load_platform(hass, "sensor", DOMAIN, {}, config)
    hass.services.async_register(DOMAIN, "mark_emptying", runtime.async_mark_emptying, schema=vol.Schema({}))
    remove_state = async_track_state_change_event(
        hass, [config[DOMAIN][key] for key in ("level_entity", "distance_entity", "threshold_entity")], runtime.recalculate,
    )
    remove_timer = async_track_time_interval(hass, runtime.async_refresh, timedelta(minutes=15))

    async def start(_event=None):
        await runtime.async_refresh()

    if hass.is_running:
        hass.async_create_task(start())
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start)

    @callback
    def stop(_event):
        remove_state()
        remove_timer()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop)
    return True
