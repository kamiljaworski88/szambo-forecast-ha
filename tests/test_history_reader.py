"""Test aggregation and Recorder adapter with explicitly stubbed HA APIs."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_model import model

ROOT = Path(__file__).resolve().parents[1] / "custom_components/septic_forecast"
START = datetime(2026, 1, 1, tzinfo=timezone.utc)
LEVEL, DISTANCE = "sensor.procent_szamba", "sensor.czujnik_szamba_distance_sensor"


def load_reader():
    # These are adapter unit tests, NOT tests on a running HA instance.
    package = ModuleType("test_septic")
    package.__path__ = [str(ROOT)]
    mocks = {"test_septic": package, "test_septic.model": model}
    for name in ("homeassistant", "homeassistant.components", "homeassistant.components.recorder", "homeassistant.components.recorder.history", "homeassistant.components.recorder.statistics", "homeassistant.core"):
        mocks[name] = ModuleType(name)
    mocks["homeassistant.components.recorder"].get_instance = Mock()
    mocks["homeassistant.components.recorder.history"].get_significant_states = Mock()
    mocks["homeassistant.components.recorder.statistics"].get_metadata = Mock()
    mocks["homeassistant.components.recorder.statistics"].statistics_during_period = Mock()
    mocks["homeassistant.core"].HomeAssistant = object
    with patch.dict(sys.modules, mocks):
        spec = importlib.util.spec_from_file_location("test_septic.history_reader", ROOT / "history_reader.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def state(hours, value, unit="%"):
    return SimpleNamespace(last_updated=START + timedelta(hours=hours), state=value, attributes={"unit_of_measurement": unit})


class HistoryReaderTests(unittest.TestCase):
    def setUp(self):
        self.reader = load_reader()

    def test_frequent_changes_still_produce_hourly_values(self):
        states = [state(i / 60, 20) for i in range(120)]
        result = self.reader.aggregate_states(states, START, START + timedelta(hours=2), lambda v, _: model.valid_number(v, 0, 100))
        self.assertEqual(list(result.values()), [20, 20])

    def test_time_weighting_is_independent_of_reporting_frequency(self):
        # 45 minutes at 20, followed by many reports at 90.
        states = [state(0, 20)] + [state(i / 60, 90) for i in range(45, 60)]
        result = self.reader.aggregate_states(states, START, START + timedelta(hours=1), lambda v, _: model.valid_number(v, 0, 100))
        self.assertEqual(list(result.values()), [20])

    def test_unknown_breaks_carry_forward(self):
        result = self.reader.aggregate_states([state(0, 20), state(1, "unavailable")], START, START + timedelta(hours=3), lambda v, _: model.valid_number(v, 0, 100))
        self.assertEqual(result[int(START.timestamp())], 20)
        self.assertIsNone(result[int(START.timestamp()) + 3600])

    def test_old_state_cannot_fill_whole_missing_days(self):
        result = self.reader.aggregate_states([state(0, 20)], START, START + timedelta(days=3), lambda v, _: model.valid_number(v, 0, 100))
        self.assertEqual(len(result), 6)

    def test_distance_units_and_range(self):
        for distance, unit in ((0.8, "m"), (80, "cm"), (800, "mm")):
            self.assertAlmostEqual(self.reader.distance_percent(distance, unit), 50)
        for value, unit in ((-1, "m"), (1.7, "m"), (1, "ft"), ("unknown", "m")):
            self.assertIsNone(self.reader.distance_percent(value, unit))

    def test_entire_long_term_history_requested_and_raw_overrides(self):
        historic = START - timedelta(days=400)
        self.reader.get_metadata.return_value = {LEVEL: (1, {"unit_of_measurement": "%"})}
        self.reader.statistics_during_period.return_value = {LEVEL: [
            {"start": historic.timestamp(), "mean": 30, "min": 29, "max": 31},
            {"start": START.timestamp(), "mean": 45, "min": 44, "max": 46},
        ]}
        self.reader.get_instance.return_value = SimpleNamespace(states_manager=SimpleNamespace(oldest_ts=START.timestamp()))
        self.reader.get_significant_states.return_value = {LEVEL: [state(0, 20)]}
        lower = datetime(2000, 1, 1, tzinfo=timezone.utc)
        result, diagnostics = self.reader.read_history(object(), LEVEL, DISTANCE, lower, START + timedelta(hours=1), True)
        self.assertEqual(result[int(historic.timestamp())], 30)
        self.assertEqual(result[int(START.timestamp())], 20)
        self.assertEqual(self.reader.statistics_during_period.call_args.args[1], lower)
        self.assertEqual(diagnostics["level_statistics_hours"], 2)

    def test_statistical_pumping_hour_is_excluded(self):
        self.reader.get_metadata.return_value = {LEVEL: (1, {"unit_of_measurement": "%"})}
        self.reader.statistics_during_period.return_value = {LEVEL: [
            {"start": START.timestamp(), "mean": 45, "min": 5, "max": 85},
        ]}
        self.reader.get_instance.return_value = SimpleNamespace(states_manager=SimpleNamespace(oldest_ts=START.timestamp()))
        self.reader.get_significant_states.return_value = {}
        result, _ = self.reader.read_history(object(), LEVEL, DISTANCE, START, START + timedelta(hours=1), True)
        self.assertIsNone(result[int(START.timestamp())])


if __name__ == "__main__":
    unittest.main()
