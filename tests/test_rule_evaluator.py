# -*- coding: utf-8 -*-
"""Unit tests for RuleEvaluator."""

import unittest

from src.core.rule_evaluator import RuleEvaluator, ConditionResult, EvaluationResult


class TestRuleEvaluatorOperators(unittest.TestCase):
    """Test each supported operator."""

    def test_less_than_pass(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "<", "value": 30}],
            {"rsi_12": 25.0},
        )
        self.assertTrue(result.all_passed)
        self.assertEqual(result.passed_count, 1)

    def test_less_than_fail(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "<", "value": 30}],
            {"rsi_12": 35.0},
        )
        self.assertFalse(result.all_passed)

    def test_less_equal(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "<=", "value": 30}],
            {"rsi_12": 30.0},
        )
        self.assertTrue(result.all_passed)

    def test_greater_than(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": ">", "value": 70}],
            {"rsi_12": 75.0},
        )
        self.assertTrue(result.all_passed)

    def test_greater_equal(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": ">=", "value": 70}],
            {"rsi_12": 70.0},
        )
        self.assertTrue(result.all_passed)

    def test_equal_string(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "kdj_signal", "operator": "==", "value": "golden_cross"}],
            {"kdj_signal": "golden_cross"},
        )
        self.assertTrue(result.all_passed)

    def test_equal_bool(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "support_ma5", "operator": "==", "value": True}],
            {"support_ma5": True},
        )
        self.assertTrue(result.all_passed)

    def test_not_equal(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "kdj_signal", "operator": "!=", "value": "dead_cross"}],
            {"kdj_signal": "golden_cross"},
        )
        self.assertTrue(result.all_passed)

    def test_in_operator(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "trend_status", "operator": "in", "value": ["强势多头", "多头排列"]}],
            {"trend_status": "多头排列"},
        )
        self.assertTrue(result.all_passed)

    def test_in_operator_fail(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "trend_status", "operator": "in", "value": ["强势多头", "多头排列"]}],
            {"trend_status": "空头排列"},
        )
        self.assertFalse(result.all_passed)

    def test_not_in_operator(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "trend_status", "operator": "not_in", "value": ["空头排列", "强势空头"]}],
            {"trend_status": "多头排列"},
        )
        self.assertTrue(result.all_passed)

    def test_between_operator_pass(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "bias_ma5", "operator": "between", "value": [-2.0, 2.0]}],
            {"bias_ma5": 0.5},
        )
        self.assertTrue(result.all_passed)

    def test_between_operator_boundary(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "bias_ma5", "operator": "between", "value": [-2.0, 2.0]}],
            {"bias_ma5": -2.0},
        )
        self.assertTrue(result.all_passed)

    def test_between_operator_fail(self):
        result = RuleEvaluator.evaluate(
            [{"indicator": "bias_ma5", "operator": "between", "value": [-2.0, 2.0]}],
            {"bias_ma5": 3.5},
        )
        self.assertFalse(result.all_passed)


class TestRuleEvaluatorEnumHandling(unittest.TestCase):
    """Test handling of enum values from TrendAnalysisResult."""

    def test_enum_value_in_list(self):
        """Enum value should match against string list."""

        class FakeEnum:
            value = "多头排列"

        result = RuleEvaluator.evaluate(
            [{"indicator": "trend_status", "operator": "in", "value": ["强势多头", "多头排列"]}],
            {"trend_status": FakeEnum()},
        )
        self.assertTrue(result.all_passed)

    def test_enum_value_equality(self):
        """Enum.value should equal its string representation."""

        class FakeEnum:
            value = "golden_cross"

        result = RuleEvaluator.evaluate(
            [{"indicator": "kdj_signal", "operator": "==", "value": "golden_cross"}],
            {"kdj_signal": FakeEnum()},
        )
        self.assertTrue(result.all_passed)


class TestRuleEvaluatorEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def test_none_indicator_value(self):
        """None actual value should always fail."""
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "<", "value": 30}],
            {"rsi_12": None},
        )
        self.assertFalse(result.all_passed)

    def test_missing_indicator(self):
        """Missing indicator in data should fail gracefully."""
        result = RuleEvaluator.evaluate(
            [{"indicator": "nonexistent", "operator": "==", "value": "x"}],
            {"rsi_12": 50.0},
        )
        self.assertFalse(result.all_passed)
        self.assertIsNone(result.details[0].actual)

    def test_unknown_operator(self):
        """Unknown operator should fail with warning."""
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "~=", "value": 30}],
            {"rsi_12": 30.0},
        )
        self.assertFalse(result.all_passed)

    def test_empty_conditions(self):
        """Empty conditions list should return all_passed=False."""
        result = RuleEvaluator.evaluate([], {"rsi_12": 50.0})
        self.assertFalse(result.all_passed)
        self.assertEqual(result.total_conditions, 0)

    def test_multiple_conditions_all_pass(self):
        result = RuleEvaluator.evaluate(
            [
                {"indicator": "rsi_12", "operator": "<", "value": 30},
                {"indicator": "kdj_signal", "operator": "==", "value": "golden_cross"},
                {"indicator": "kdj_k", "operator": "<", "value": 30},
            ],
            {"rsi_12": 25.0, "kdj_signal": "golden_cross", "kdj_k": 18.0},
        )
        self.assertTrue(result.all_passed)
        self.assertEqual(result.passed_count, 3)

    def test_multiple_conditions_partial_pass(self):
        result = RuleEvaluator.evaluate(
            [
                {"indicator": "rsi_12", "operator": "<", "value": 30},
                {"indicator": "kdj_signal", "operator": "==", "value": "golden_cross"},
                {"indicator": "kdj_k", "operator": "<", "value": 30},
            ],
            {"rsi_12": 25.0, "kdj_signal": "dead_cross", "kdj_k": 18.0},
        )
        self.assertFalse(result.all_passed)
        self.assertEqual(result.passed_count, 2)
        self.assertAlmostEqual(result.pass_rate, 2 / 3, places=3)

    def test_to_dict(self):
        """EvaluationResult.to_dict() should be serializable."""
        result = RuleEvaluator.evaluate(
            [{"indicator": "rsi_12", "operator": "<", "value": 30}],
            {"rsi_12": 25.0},
        )
        d = result.to_dict()
        self.assertIn("all_passed", d)
        self.assertIn("details", d)
        self.assertEqual(len(d["details"]), 1)
        self.assertTrue(d["details"][0]["passed"])


if __name__ == "__main__":
    unittest.main()
