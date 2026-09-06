import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_visual_density import density_summary, parse_visuals


class VisualDensityTests(unittest.TestCase):
    def test_parse_and_summarize_aux_entries(self):
        aux = "\n".join(
            [
                r"\@writefile{lof}{\contentsline {figure}{\numberline {1}{One}}{2}{figure.1}\protected@file@percent }",
                r"\@writefile{lot}{\contentsline {table}{\numberline {1}{Two}}{5}{table.1}\protected@file@percent }",
                r"\@writefile{lof}{\addvspace {10\p@ }}",
            ]
        )
        summary = density_summary(parse_visuals(aux))
        self.assertEqual(summary["figures"], 1)
        self.assertEqual(summary["tables"], 1)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["body_pages"], 5)
        self.assertEqual(summary["largest_page_gap"], 3)
        self.assertEqual(summary["pages_per_visual"], 2.5)

    def test_empty_aux_is_explicit(self):
        summary = density_summary(parse_visuals(""))
        self.assertEqual(summary["total"], 0)
        self.assertEqual(summary["pages_per_visual"], float("inf"))


if __name__ == "__main__":
    unittest.main()
