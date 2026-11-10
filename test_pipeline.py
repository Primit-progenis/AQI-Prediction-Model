import datetime as dt
import math
import unittest

import pipeline


class PipelineContractTests(unittest.TestCase):
    def test_leakage_cutoff_accepts_origin_and_rejects_future(self):
        origin = dt.datetime.fromisoformat("2026-11-10T09:00:00+05:30")
        pipeline.assert_feature_cutoff([origin - dt.timedelta(hours=1), origin], origin)
        with self.assertRaises(AssertionError):
            pipeline.assert_feature_cutoff([origin + dt.timedelta(hours=1)], origin)

    def test_submission_contract(self):
        sample = pipeline.read_csv(pipeline.ROOT / "SampleSubmission.csv")
        test = pipeline.read_csv(pipeline.ROOT / "Test.csv")
        self.assertEqual(len(sample), 2592)
        self.assertEqual([x["ID"] for x in sample], [x["ID"] for x in test])
        for filename in ("submission_primary.csv", "submission_hedged.csv"):
            rows = pipeline.read_csv(pipeline.SUBMISSION_DIR / filename)
            self.assertEqual(len(rows), 2592)
            self.assertEqual([x["ID"] for x in rows], [x["ID"] for x in sample])
            for row in rows:
                target = float(row["Target"])
                self.assertTrue(math.isfinite(target))
                self.assertGreaterEqual(target, 0)

    def test_predictions_are_invariant_to_rows_after_origin(self):
        origin = dt.datetime.fromisoformat("2026-05-10T09:00:00+05:30")
        full = {sid: {} for sid in pipeline.STATIONS}
        for sid_i, sid in enumerate(pipeline.STATIONS):
            for hour in range(14 * 24 + 1):
                stamp = origin - dt.timedelta(hours=14 * 24 - hour)
                full[sid][stamp] = 30.0 + sid_i * 5.0 + (stamp.hour % 7)
            for hour in range(1, 65):
                full[sid][origin + dt.timedelta(hours=hour)] = 800.0 + hour
        truncated = {sid: {t: v for t, v in values.items() if t <= origin}
                     for sid, values in full.items()}
        pipeline.SERIES_CACHE.clear()
        full_predictions, _ = pipeline.predictions_at(full, origin, range(16, 64))
        pipeline.SERIES_CACHE.clear()
        truncated_predictions, _ = pipeline.predictions_at(truncated, origin, range(16, 64))
        self.assertEqual(full_predictions, truncated_predictions)

    def test_private_window_is_192_rows_at_horizons_16_through_63(self):
        test = pipeline.read_csv(pipeline.ROOT / "Test.csv")
        t0 = dt.datetime.fromisoformat(pipeline.T0_EXPECTED)
        private = pipeline.select_private_window(test, t0)
        horizons = {
            int((dt.datetime.fromisoformat(row["target_end_ist"]) - t0).total_seconds() / 3600)
            for row in private
        }
        self.assertEqual(len(private), 192)
        self.assertEqual(horizons, set(range(16, 64)))

    def test_public_interval_files_match_primary_submission(self):
        test = pipeline.read_csv(pipeline.ROOT / "Test.csv")
        primary = pipeline.read_csv(pipeline.SUBMISSION_DIR / "submission_primary.csv")
        primary_by_id = {row["ID"]: row["Target"] for row in primary}
        interval_dir = pipeline.ROOT / "Submission" / "02_Public_Intervals"
        for filename, start, end in pipeline.PUBLIC_INTERVALS:
            expected = [row for row in test if start <= dt.datetime.fromisoformat(row["target_end_ist"]).date() <= end]
            actual = pipeline.read_csv(interval_dir / filename)
            self.assertEqual([row["ID"] for row in actual], [row["ID"] for row in expected])
            self.assertEqual([row["Target"] for row in actual], [primary_by_id[row["ID"]] for row in expected])


if __name__ == "__main__":
    unittest.main()
