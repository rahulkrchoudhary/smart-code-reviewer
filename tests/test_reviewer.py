"""Tests for the review engine.

A code-quality tool ought to be well-tested itself. These use the stdlib
`unittest` runner (no extra dependencies) and exercise the static engine and
scoring — the parts that run with no API key.

    python -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

# Make the package importable when running the file directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import reviewer  # noqa: E402
from reviewer import Dimension, Severity  # noqa: E402


CLEAN = '''\
"""A tidy module that should score well."""

DISCOUNT_RATE = 0.1


def discounted_price(price: float) -> float:
    """Return the price after the standard discount."""
    return price * (1 - DISCOUNT_RATE)
'''

MESSY = '''\
def processData(d, l=[]):
    try:
        return eval("1+" + str(d))
    except:
        pass
'''

MESSY_JS = """\
var x = 1;
function f(a) {
  if (a == 1) { console.log(a); }
}
"""


def _titles(result):
    return {f.title for f in result.findings}


class LanguageDetection(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(reviewer.detect_language("a.py"), "Python")
        self.assertEqual(reviewer.detect_language("a.ts"), "TypeScript")
        self.assertEqual(reviewer.detect_language("a.go"), "Go")

    def test_by_content(self):
        self.assertEqual(reviewer.detect_language("", "def go():\n    self.x"),
                         "Python")


class CleanCode(unittest.TestCase):
    def setUp(self):
        self.result = reviewer.review(CLEAN, "Python")

    def test_grades_well(self):
        self.assertGreaterEqual(self.result.overall_score, 90)
        self.assertEqual(self.result.overall_grade, "A")

    def test_no_serious_findings(self):
        counts = self.result.counts_by_severity()
        self.assertEqual(counts[Severity.CRITICAL], 0)
        self.assertEqual(counts[Severity.MAJOR], 0)

    def test_named_constant_not_flagged_as_magic(self):
        magic = [f for f in self.result.findings if f.rule_id == "PY-MAGIC"]
        self.assertEqual(magic, [])


class MessyCode(unittest.TestCase):
    def setUp(self):
        self.result = reviewer.review(MESSY, "Python")

    def test_catches_the_big_three(self):
        titles = _titles(self.result)
        self.assertIn("Use of `eval`", titles)
        self.assertIn("Bare except", titles)
        self.assertIn("Mutable default argument", titles)

    def test_eval_is_critical(self):
        eval_finding = next(f for f in self.result.findings
                            if f.title == "Use of `eval`")
        self.assertEqual(eval_finding.severity, Severity.CRITICAL)
        self.assertEqual(eval_finding.dimension, Dimension.MAINTAINABILITY)

    def test_scores_lower_than_clean(self):
        clean = reviewer.review(CLEAN, "Python")
        self.assertLess(self.result.overall_score, clean.overall_score)

    def test_every_finding_has_a_suggestion(self):
        # Actionable feedback is the whole point.
        for f in self.result.findings:
            self.assertTrue(f.suggestion, f"no suggestion on: {f.title}")


class JavaScriptHeuristics(unittest.TestCase):
    def setUp(self):
        self.result = reviewer.review(MESSY_JS, "JavaScript")

    def test_flags_loose_equality_and_var(self):
        rules = {f.rule_id for f in self.result.findings}
        self.assertIn("JS-LOOSEEQ", rules)
        self.assertIn("JS-VAR", rules)
        self.assertIn("JS-DEBUG", rules)


class Scoring(unittest.TestCase):
    def test_dimension_scores_bounded(self):
        result = reviewer.review(MESSY, "Python")
        for dim in Dimension:
            score = result.dimension_scores[dim].score
            self.assertGreaterEqual(score, 0)
            self.assertLessEqual(score, 100)

    def test_empty_input_is_safe(self):
        result = reviewer.review("", "Python")
        self.assertEqual(result.findings, [])
        self.assertEqual(result.overall_grade, "A")


if __name__ == "__main__":
    unittest.main(verbosity=2)
