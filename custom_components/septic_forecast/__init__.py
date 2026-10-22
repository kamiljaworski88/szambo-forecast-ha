"""Local forecast with UI setup, YAML import and persisted Recorder cycles."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from functools import partial
import logging

import voluptuous as vol

from homeassistant.components.recorder import get_instance, is_entity_recorded
from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
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
        self.threshold = float(config.get("threshold", 90))
        self.stopped = False
        self.unsubscribers = []

    async def async_load(self) -> None:
        if (data := await self.store.async_load()) and data.get("sources") == self.sources:
            self.hours = {int(t): v for t, v in data.get("hours", [])}
            self.markers = data.get("manual_emptyings", [])
            self.cursor = data.get("cursor")
            self.diagnostics = data.get("diagnostics", {})
            self.threshold = valid_number(data.get("threshold", self.threshold), 1, 100) or 90.0

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
            "threshold": self.threshold,
        }

    @callback
    def recalculate(self, _event=None) -> None:
        if self.stopped:
            return
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
        threshold_id = self.config.get("threshold_entity")
        threshold = self.hass.states.get(threshold_id) if threshold_id else None
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
            target = (threshold.state if threshold else None) if threshold_id else self.threshold
            drop = self.config["emptying_drop"]
            self.result = await self.hass.async_add_executor_job(
                lambda: predict(as_points(hours), markers, now, zone, level, target, source_valid=valid, drop=drop)
            )
        if not self._dirty:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE)

    async def async_refresh(self, _now=None) -> None:
        if self.stopped or self.lock.locked():
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

    async def async_set_threshold(self, value: float) -> None:
        target = valid_number(value, 1, 100)
        if target is None:
            raise HomeAssistantError("Próg musi mieścić się w zakresie 1–100%")
        async with self.lock:
            previous = self.threshold
            self.threshold = target
            try:
                await self.store.async_save(self.snapshot())
            except Exception:
                self.threshold = previous
                raise
            self.recalculate()

    async def async_stop(self) -> None:
        self.stopped = True
        for remove in self.unsubscribers:
            remove()
        self.unsubscribers.clear()
        if self._calculation is not None and not self._calculation.done():
            self._calculation.cancel()
            await asyncio.gather(self._calculation, return_exceptions=True)
        async with self.lock:
            await self.store.async_save(self.snapshot())

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
    if DOMAIN in config:
        imported = dict(config[DOMAIN])
        imported["history_start"] = str(imported["history_start"])
        hass.async_create_task(hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_IMPORT}, data=imported,
        ))
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    settings = {
        "level_entity": DEFAULT_LEVEL, "distance_entity": DEFAULT_DISTANCE,
        "threshold_entity": None, "threshold": 90,
        "history_start": "2000-01-01", "emptying_drop": 15.0,
        **entry.data, **entry.options,
    }
    settings["history_start"] = cv.date(settings["history_start"])
    runtime = ForecastRuntime(hass, settings)
    await runtime.async_load()
    entry.runtime_data = runtime
    hass.data[DOMAIN] = runtime
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor", "number"])
    hass.services.async_register(DOMAIN, "mark_emptying", runtime.async_mark_emptying, schema=vol.Schema({}))
    sources = [settings[key] for key in ("level_entity", "distance_entity", "threshold_entity") if settings[key]]
    runtime.unsubscribers.extend([
        async_track_state_change_event(hass, sources, runtime.recalculate),
        async_track_time_interval(hass, runtime.async_refresh, timedelta(minutes=15)),
    ])

    async def start(_event=None):
        await runtime.async_refresh()

    def listen_once(event_type, handler):
        async def once(event):
            if remove in runtime.unsubscribers:
                runtime.unsubscribers.remove(remove)
            await handler(event)

        remove = hass.bus.async_listen_once(event_type, once)
        runtime.unsubscribers.append(remove)

    if hass.is_running:
        hass.async_create_task(start())
    else:
        listen_once(EVENT_HOMEASSISTANT_STARTED, start)

    async def stop(_event):
        await runtime.async_stop()

    listen_once(EVENT_HOMEASSISTANT_STOP, stop)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, ["sensor", "number"]):
        return False
    await entry.runtime_data.async_stop()
    hass.services.async_remove(DOMAIN, "mark_emptying")
    hass.data.pop(DOMAIN, None)
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
