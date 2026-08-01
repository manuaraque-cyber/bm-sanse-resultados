import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import actualizar_datos_web as updater


DATE = "2026-07-31"


def sample_day(score="2-0"):
    return {
        "date": DATE,
        "tournament": "Campeonato de España Laredo",
        "summary": {"matches": 1, "victories": 1, "defeats": 0, "others": 0},
        "results": [{"score": score, "outcome": "Victoria"}],
        "categoriesWithoutMatches": [],
        "warnings": [],
    }


def sample_dataset(day):
    stored_day = copy.deepcopy(day)
    stored_day["generatedAt"] = "2026-08-01T10:00:00Z"
    return {
        "tournament": "Campeonato de España Laredo",
        "generatedAt": "2026-08-01T10:00:00Z",
        "categories": list(updater.CATEGORIES),
        "dates": {DATE: stored_day},
    }


class UpdateDataTests(unittest.TestCase):
    def run_updater(self, output, returned_day):
        arguments = ["actualizar_datos_web.py", DATE, "--salida", str(output)]
        with mock.patch.object(updater, "query_date", return_value=returned_day):
            with mock.patch.object(sys, "argv", arguments):
                return updater.main()

    def test_does_not_rewrite_when_results_are_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "resultados.json"
            original = json.dumps(sample_dataset(sample_day()), ensure_ascii=False, indent=2) + "\n"
            output.write_text(original, encoding="utf-8")

            self.assertEqual(self.run_updater(output, sample_day()), 0)
            self.assertEqual(output.read_text(encoding="utf-8"), original)

    def test_rewrites_when_score_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "resultados.json"
            output.write_text(
                json.dumps(sample_dataset(sample_day("1-2")), ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            self.assertEqual(self.run_updater(output, sample_day("2-0")), 0)
            updated = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(updated["dates"][DATE]["results"][0]["score"], "2-0")
            self.assertNotEqual(updated["generatedAt"], "2026-08-01T10:00:00Z")


if __name__ == "__main__":
    unittest.main()
