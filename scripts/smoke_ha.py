"""Real HA Core smoke test on disposable SQLite, never production config.

Run with Python 3.13 and homeassistant==2025.10.4. Does not use mocks.
"""

import asyncio
from datetime import timedelta
import logging
from pathlib import Path
import tempfile
import sys

from homeassistant.core import HomeAssistant
from homeassistant import loader
from homeassistant.bootstrap import async_load_base_functionality
from homeassistant.config_entries import ConfigEntries
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.setup import async_setup_component
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.recorder.models.statistics import StatisticMeanType
from homeassistant.helpers.template import Template
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
import yaml

ROOT = Path(__file__).resolve().parents[1]


async def run(ui=False):
    logged_errors = []

    class ErrorCapture(logging.Handler):
        def emit(self, record):
            if record.levelno >= logging.ERROR:
                logged_errors.append(record.getMessage())

    capture = ErrorCapture()
    logging.getLogger().addHandler(capture)
    with tempfile.TemporaryDirectory(prefix="septic-ha-test-") as directory:
        path = Path(directory)
        (path / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(str(path))
        loader.async_setup(hass)
        package = yaml.safe_load((ROOT / "examples/package_szambo.yaml").read_text())
        config = {
            "homeassistant": {"time_zone": "Europe/Warsaw", "country": "PL"},
            "recorder": {"db_url": f"sqlite:///{path / 'test.db'}", "commit_interval": 1},
            **({} if ui else package),
        }
        try:
            # Minimal Core bootstrap: no frontend, HTTP listener or network scan.
            hass.config_entries = ConfigEntries(hass, config)
            await async_load_base_functionality(hass)
            await async_process_ha_core_config(hass, config["homeassistant"])
            async_initialize_recorder(hass)
            for domain in ("homeassistant", "recorder") + (() if ui else ("input_number",)):
                assert await async_setup_component(hass, domain, config)
            hass.states.async_set("sensor.procent_szamba", "30", {"unit_of_measurement": "%"})
            hass.states.async_set("sensor.czujnik_szamba_distance_sensor", "1.12", {"unit_of_measurement": "m"})
            ui_data = {"level_entity": "sensor.procent_szamba", "distance_entity": "sensor.czujnik_szamba_distance_sensor", "threshold": 90, "history_start": "2000-01-01", "emptying_drop": 15}
            if not ui:
                # An archive and entity registry record shaped like version 0.1.0.
                sentinel = int((dt_util.utcnow() - timedelta(hours=12)).timestamp() // 3600 * 3600)
                await Store(hass, 1, "septic_forecast").async_save({
                    "sources": [ui_data["level_entity"], ui_data["distance_entity"], "2000-01-01"],
                    "hours": [[sentinel, 20]], "manual_emptyings": [sentinel - 86400],
                    "cursor": None, "diagnostics": {},
                })
                previous_entity = er.async_get(hass).async_get_or_create(
                    "sensor", "septic_forecast", "septic_forecast_dni", suggested_object_id="szambo_dni_do_odbioru",
                )
                previous_entity_id = previous_entity.id
            assert await async_setup_component(hass, "septic_forecast", config)
            if ui:
                form = await hass.config_entries.flow.async_init("septic_forecast", context={"source": "user"})
                assert form["type"] == "form"
                bad = await hass.config_entries.flow.async_configure(form["flow_id"], {**ui_data, "distance_entity": ui_data["level_entity"]})
                assert bad["errors"]["base"] == "same_entity"
                created = await hass.config_entries.flow.async_configure(form["flow_id"], ui_data)
                assert created["type"] == "create_entry", created
            await hass.async_start()
            # Wait for the startup import and platform setup.
            await hass.async_block_till_done()
            runtime = hass.data["septic_forecast"]
            entries = hass.config_entries.async_entries("septic_forecast")
            assert len(entries) == 1
            entry = entries[0]
            assert entry.source == ("user" if ui else "import")
            await runtime.async_refresh()
            await hass.async_block_till_done()
            assert not runtime.error, "Recorder API import failed"
            expected = (
                "sensor.szambo_dni_do_odbioru", "sensor.szambo_przewidywana_data_odbioru",
                "sensor.szambo_tempo_napelniania", "sensor.szambo_wiarygodnosc_prognozy",
            )
            for entity_id in expected:
                assert hass.states.get(entity_id) is not None, entity_id
            assert hass.states.get(expected[0]).state == "unknown"
            threshold_id = "number.szambo_prognoza_prog" if ui else "input_number.szambo_prognoza_prog"
            assert float(hass.states.get(threshold_id).state) == 90
            if not ui:
                assert sentinel in runtime.hours and runtime.markers == [sentinel - 86400]
                migrated = er.async_get(hass).async_get(expected[0])
                assert migrated.id == previous_entity_id and migrated.config_entry_id == entry.entry_id
                assert hass.states.get(expected[0] + "_2") is None
            runtime.markers = []  # All following measurements are synthetic test data.
            duplicate = await hass.config_entries.flow.async_init("septic_forecast", context={"source": "user"})
            assert duplicate["type"] == "abort" and duplicate["reason"] == "single_instance_allowed"

            # Synthetic data in REAL long-term SQLite tables, not model injection.
            now = dt_util.utcnow()
            start = (now - timedelta(days=10)).replace(hour=0, minute=0, second=0, microsecond=0)
            samples = {
                start + timedelta(hours=i): 10 + 2 * i / 24
                for i in range(int((now - start).total_seconds() // 3600))
            }
            old = (start - timedelta(days=400))
            samples[old] = 30
            async_import_statistics(hass, {
                "statistic_id": "sensor.procent_szamba", "source": "recorder",
                "unit_of_measurement": "%", "name": None,
                "has_sum": False, "mean_type": StatisticMeanType.ARITHMETIC,
            }, [
                {"start": timestamp, "mean": value, "min": value - 0.01, "max": value + 0.01}
                for timestamp, value in samples.items()
            ])
            await hass.async_add_executor_job(get_instance(hass).block_till_done)
            runtime.cursor = None
            await runtime.async_refresh()
            assert not runtime.error
            assert int(old.timestamp()) in runtime.hours, "Long-term history was truncated"
            current = samples[max(samples)]
            hass.states.async_set("sensor.procent_szamba", str(current), {"unit_of_measurement": "%"})
            hass.states.async_set("sensor.czujnik_szamba_distance_sensor", str(1.6 * (1 - current / 100)), {"unit_of_measurement": "m"})
            await hass.async_block_till_done()
            assert runtime.result.rate is not None and abs(runtime.result.rate - 2) < 0.05
            card = yaml.safe_load((ROOT / ("examples/dashboard_szambo_ui.yaml" if ui else "examples/dashboard_szambo.yaml")).read_text())
            rendered = Template(card["cards"][1]["content"], hass).async_render()
            assert "Około" in rendered and "przewidywany próg" in rendered, rendered
            original_days = runtime.result.days
            await hass.services.async_call("number" if ui else "input_number", "set_value", {"entity_id": threshold_id, "value": 85}, blocking=True)
            await hass.async_block_till_done()
            assert runtime.result.days < original_days

            await hass.services.async_call("septic_forecast", "mark_emptying", {}, blocking=True)
            await hass.async_block_till_done()
            assert runtime.result.days is None
            assert len(runtime.markers) == 1
            data = await runtime.store.async_load()
            assert len(data["manual_emptyings"]) == 1
            restored = type(runtime)(hass, runtime.config)
            await restored.async_load()
            assert restored.markers == runtime.markers
            assert restored.hours == runtime.hours
            if ui:
                # Options must reload cleanly and preserve threshold, archive and IDs.
                entity_ids = {item.entity_id for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
                options = await hass.config_entries.options.async_init(entry.entry_id)
                assert options["type"] == "form"
                option_data = {key: value for key, value in ui_data.items() if key != "threshold"}
                await hass.config_entries.options.async_configure(options["flow_id"], {**option_data, "emptying_drop": 20})
                await hass.async_block_till_done()
                runtime = hass.data["septic_forecast"]
                assert runtime.config["emptying_drop"] == 20 and runtime.threshold == 85
                assert len(runtime.markers) == 1
                assert entity_ids == {item.entity_id for item in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}
                # A missing helper / recursive reference must not be accepted.
                options = await hass.config_entries.options.async_init(entry.entry_id)
                bad = await hass.config_entries.options.async_configure(options["flow_id"], {**option_data, "threshold_entity": threshold_id})
                assert bad["errors"]["threshold_entity"] == "own_threshold"
                hass.config_entries.options.async_abort(options["flow_id"])
                assert await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()
                assert "septic_forecast" not in hass.data
                assert not hass.services.has_service("septic_forecast", "mark_emptying")
                assert await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()
                runtime = hass.data["septic_forecast"]
                assert runtime.threshold == 85 and len(runtime.markers) == 1
            print(f"HA Core smoke ({'UI' if ui else 'YAML migration'}): configuration, Recorder >400 days, entities, threshold, dashboard, persistence and lifecycle OK")
        finally:
            await hass.async_stop()
            logging.getLogger().removeHandler(capture)
        assert not logged_errors, logged_errors


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run(ui="--ui" in sys.argv))
