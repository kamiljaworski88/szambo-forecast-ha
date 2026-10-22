"""Real numerical scenarios; no mocked Home Assistant claimed as runtime QA."""

from datetime import datetime, timedelta, timezone
import importlib.util
from pathlib import Path
import sys
import unittest
from zoneinfo import ZoneInfo

PATH = Path(__file__).resolve().parents[1] / "custom_components/septic_forecast/model.py"
spec = importlib.util.spec_from_file_location("septic_model", PATH)
model = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = model
spec.loader.exec_module(model)

UTC = timezone.utc
START = datetime(2026, 1, 1, tzinfo=UTC)


def series(days=10, rate=2, base=10, start=START, hours_per_day=24):
    return [
        model.Point((start + timedelta(days=day, hours=hour)).timestamp(), base + rate * (day + hour / 24))
        for day in range(days) for hour in range(hours_per_day)
    ]


def forecast(points, level=None, now=None, markers=None, **kwargs):
    now = now or datetime.fromtimestamp(points[-1].timestamp, UTC) + timedelta(hours=1)
    return model.predict(points, markers or [], now, UTC, level if level is not None else points[-1].value, 90, **kwargs)


class ForecastTests(unittest.TestCase):
    def test_three_days_are_required(self):
        result = forecast(series(days=2))
        self.assertIsNone(result.days)
        self.assertIn("krótki", result.reason)

    def test_linear_growth_formula_and_date(self):
        result = forecast(series(days=10))
        self.assertAlmostEqual(result.rate, 2)
        self.assertAlmostEqual(result.days, (90 - (10 + 2 * (9 + 23 / 24))) / 2)
        self.assertAlmostEqual((result.date - (START + timedelta(days=10))).total_seconds(), result.days * 86400)
        self.assertEqual(result.confidence, "ograniczona")

    def test_zero_and_negative_growth(self):
        for rate in (0, -0.2):
            with self.subTest(rate=rate):
                result = forecast(series(rate=rate))
                self.assertIsNone(result.days)
                self.assertIsNone(result.rate)

    def test_invalid_live_values(self):
        points = series()
        for value in ("unknown", "unavailable", None, -1, 101, float("nan"), float("inf")):
            with self.subTest(value=value):
                result = forecast(points, level=value if value is not None else "unknown")
                self.assertIsNone(result.days)

    def test_inconsistent_or_stale_live_source(self):
        self.assertIsNone(forecast(series(), source_valid=False).days)

    def test_isolated_spikes_do_not_change_trend(self):
        points = series()
        points[80] = model.Point(points[80].timestamp, 95)
        points[130] = model.Point(points[130].timestamp, 0)
        result = forecast(points)
        self.assertAlmostEqual(result.rate, 2, places=2)
        self.assertEqual(result.detected_emptyings, 0)
        self.assertGreaterEqual(result.rejected_hours, 2)

    def test_latest_anomaly_blocks_forecast(self):
        self.assertIsNone(forecast(series(), level=90).days)

    def test_emptying_pending_then_confirmed(self):
        points = series(days=10, base=60)
        first = model.Point(points[-1].timestamp + 3600, 5)
        pending = forecast(points + [first])
        self.assertIsNone(pending.days)
        self.assertIn("potwierdzenie", pending.reason)
        second = model.Point(first.timestamp + 3600, 5.1)
        result = forecast(points + [first, second])
        self.assertIsNone(result.days)
        self.assertEqual(result.detected_emptyings, 1)

    def test_complete_cycles_are_reference_not_one_global_slope(self):
        points = series(days=12, base=60, rate=2)
        # First visible cycle has no known beginning and must not count as full.
        points += series(days=12, base=5, rate=2, start=START + timedelta(days=12))
        points += series(days=12, base=5, rate=3, start=START + timedelta(days=24))
        result = forecast(points)
        self.assertEqual(result.complete_cycles, 1)
        self.assertEqual(result.detected_emptyings, 2)
        self.assertAlmostEqual(result.historical_rate, 2)
        self.assertAlmostEqual(result.current_rate, 3)
        self.assertAlmostEqual(result.current_weight, 0.9)
        self.assertAlmostEqual(result.rate, 2.9)
        self.assertEqual(result.confidence, "wysoka")

    def test_manual_marker_starts_new_cycle_and_survives_replay(self):
        points = series(days=10)
        marker = points[-1].timestamp + 1800
        result = forecast(points, markers=[marker])
        self.assertIsNone(result.days)
        extra = series(days=5, base=5, rate=3, start=START + timedelta(days=10))
        for _ in range(2):
            result = forecast(points + extra, markers=[marker])
            self.assertAlmostEqual(result.rate, 3)
            self.assertEqual(result.current_days, 5)

    def test_history_older_than_fourteen_days_is_used(self):
        points = series(days=35, base=5, rate=1)
        result = forecast(points)
        self.assertEqual(result.current_days, 35)
        self.assertAlmostEqual(result.rate, 1)

    def test_recent_stagnation_blocks_old_positive_slope(self):
        points = series(days=15)
        points += series(days=8, rate=0, base=40, start=START + timedelta(days=15))
        self.assertIsNone(forecast(points).days)

    def test_long_gap_breaks_cycle(self):
        points = series(days=10)
        points += series(days=2, start=START + timedelta(days=20), base=50)
        result = forecast(points)
        self.assertIsNone(result.days)
        self.assertEqual(result.current_days, 2)

    def test_sparse_hourly_history_is_not_daily_evidence(self):
        points = series(days=10, hours_per_day=3)
        result = forecast(points)
        self.assertIsNone(result.days)

    def test_target_reached_and_threshold_change(self):
        points = series(days=5, base=85, rate=1)
        now = START + timedelta(days=5)
        result = model.predict(points, [], now, UTC, 89.9, 89)
        self.assertEqual(result.days, 0)
        result = model.predict(points, [], now, UTC, 89.9, 95)
        self.assertAlmostEqual(result.days, 5.1)

    def test_stale_archived_history_is_rejected(self):
        points = series()
        result = forecast(points, now=START + timedelta(days=11))
        self.assertIsNone(result.days)

    def test_dst_local_day_binning(self):
        start = datetime(2026, 10, 22, tzinfo=UTC)
        points = series(days=8, start=start)
        result = model.predict(points, [], start + timedelta(days=8), ZoneInfo("Europe/Warsaw"), points[-1].value, 90)
        self.assertIsNotNone(result.days)
        self.assertAlmostEqual(result.rate, 2, delta=0.05)

    def test_jagged_daily_trend_is_rejected(self):
        points = series(days=12, rate=0)
        points = [model.Point(p.timestamp, p.value + (p.timestamp - START.timestamp()) / 86400 * 1.5 + (6 if int((p.timestamp - START.timestamp()) / 86400) % 2 else 0)) for p in points]
        result = forecast(points)
        self.assertIsNone(result.days)


if __name__ == "__main__":
    unittest.main()
