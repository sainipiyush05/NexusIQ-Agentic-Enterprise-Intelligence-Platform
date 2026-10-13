import csv
import os
import tempfile
import unittest
from pathlib import Path

from nexusiq.olist import FILES, inspect_source, search_reviews, status


class OlistSourceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        for filename, _, columns in FILES:
            with (self.directory / filename).open("w", newline="", encoding="utf-8") as stream:
                csv.writer(stream).writerow(columns)

    def test_inspect_source_records_counts_and_hashes(self):
        report = inspect_source(self.directory)
        self.assertEqual(set(report["row_counts"]), {table for _, table, _ in FILES})
        self.assertTrue(all(count == 0 for count in report["row_counts"].values()))
        self.assertTrue(all(len(item["sha256"]) == 64 for item in report["files"].values()))

    def test_header_and_row_shape_fail_closed(self):
        source = self.directory / FILES[0][0]
        source.write_text("wrong,column\n")
        with self.assertRaisesRegex(ValueError, "Unexpected columns"):
            inspect_source(self.directory)
        with source.open("w", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(FILES[0][2])
            writer.writerow(["short"])
        with self.assertRaisesRegex(ValueError, "Malformed CSV row"):
            inspect_source(self.directory)

    def test_search_rejects_invalid_query_and_limit_before_connecting(self):
        for query, limit in (("", 5), ("a" * 501, 5), ("term", 0), ("term", True)):
            with self.subTest(query=query[:10], limit=limit), self.assertRaises(ValueError):
                search_reviews(query, limit)


@unittest.skipUnless(os.environ.get("NEXUSIQ_OLIST_TESTS") == "1",
                     "Set NEXUSIQ_OLIST_TESTS=1 after a live Olist import")
class OlistIntegrationTests(unittest.TestCase):
    def test_live_counts_and_review_search(self):
        report = status()
        self.assertGreaterEqual(report["business_rows"], 100000)
        self.assertGreaterEqual(report["review_text_units"], 2500)
        hits = search_reviews("produto", limit=3)
        self.assertTrue(hits)
        self.assertTrue(all(hit["order_id"] and hit["review_id"] for hit in hits))

    def test_live_olist_benchmark(self):
        from nexusiq.olist_eval import run_benchmark
        report = run_benchmark()
        self.assertEqual(report["retrieval_benchmark"]["hit_rate"], 1.0)
        self.assertGreater(report["retrieval_benchmark"]["sentiment_accuracy"], 0.8)
        self.assertGreater(report["sql_analytics_benchmark"]["total_rows_scanned_in_benchmark"], 500000)


if __name__ == "__main__":
    unittest.main()
