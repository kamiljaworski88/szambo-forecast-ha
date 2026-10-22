"""Real HA Core smoke test on disposable SQLite, never production config.

Run with Python 3.13 and homeassistant==2025.10.4. Does not use mocks.
"""

import asyncio
from datetime import timedelta
import logging
from pathlib import Path
import tempfile

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
from homeassistant.util import dt as dt_util
import yaml

ROOT = Path(__file__).resolve().parents[1]


async def run():
    with tempfile.TemporaryDirectory(prefix="septic-ha-test-") as directory:
        path = Path(directory)
        (path / "custom_components").symlink_to(ROOT / "custom_components", target_is_directory=True)
        hass = HomeAssistant(str(path))
        loader.async_setup(hass)
        package = yaml.safe_load((ROOT / "examples/package_szambo.yaml").read_text())
        config = {
            "homeassistant": {"time_zone": "Europe/Warsaw", "country": "PL"},
            "recorder": {"db_url": f"sqlite:///{path / 'test.db'}", "commit_interval": 1},
            **package,
        }
        try:
            # Minimal Core bootstrap: no frontend, HTTP listener or network scan.
            hass.config_entries = ConfigEntries(hass, config)
            await async_load_base_functionality(hass)
            await async_process_ha_core_config(hass, config["homeassistant"])
            async_initialize_recorder(hass)
            for domain in ("homeassistant", "recorder", "input_number", "septic_forecast"):
                assert await async_setup_component(hass, domain, config)
            assert "septic_forecast" in hass.config.components
            hass.states.async_set("sensor.procent_szamba", "30", {"unit_of_measurement": "%"})
            hass.states.async_set("sensor.czujnik_szamba_distance_sensor", "1.12", {"unit_of_measurement": "m"})
            await hass.async_start()
            runtime = hass.data["septic_forecast"]
            # Wait for the startup import and platform setup.
            await hass.async_block_till_done()
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
            assert hass.states.get("input_number.szambo_prognoza_prog").state == "90.0"

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
            card = yaml.safe_load((ROOT / "examples/dashboard_szambo.yaml").read_text())
            rendered = Template(card["cards"][1]["content"], hass).async_render()
            assert "Około" in rendered and "przewidywany próg" in rendered, rendered
            original_days = runtime.result.days
            await hass.services.async_call("input_number", "set_value", {"entity_id": "input_number.szambo_prognoza_prog", "value": 85}, blocking=True)
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
            print("HA Core smoke: setup, real SQLite statistics >400 days old, four sensors, helper, forecast, dashboard template, threshold change, manual reset and archive reload OK")
        finally:
            await hass.async_stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run())
