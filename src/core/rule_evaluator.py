# -*- coding: utf-8 -*-
"""Evaluate quantitative_rules conditions against TrendAnalysisResult.

This module provides a structured condition evaluation engine that checks
buy/sell conditions defined in strategy YAML ``quantitative_rules`` against
live indicator data from ``TrendAnalysisResult``.

Supported operators:
    ``<``, ``<=``, ``>``, ``>=``, ``==``, ``!=``, ``in``, ``not_in``, ``between``
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _to_comparable(value: Any) -> Any:
    """Convert enum values to their string representation for comparison."""
    if hasattr(value, "value"):
        return value.value
    return value


def _eq(a: Any, b: Any) -> bool:
    """Flexible equality: handles enum.value vs string comparison."""
    a = _to_comparable(a)
    b = _to_comparable(b)
    # Handle bool vs string comparison
    if isinstance(b, bool):
        if isinstance(a, bool):
            return a == b
        return False
    if isinstance(a, bool) and isinstance(b, str):
        return str(a).lower() == b.lower()
    return str(a) == str(b)


def _to_str_list(items: List[Any]) -> List[str]:
    """Convert a list of values to comparable strings."""
    return [str(_to_comparable(x)) for x in items]


@dataclass
class ConditionResult:
    """Single condition evaluation result."""

    indicator: str
    operator: str
    expected: Any
    actual: Any
    passed: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "indicator": self.indicator,
            "operator": self.operator,
            "expected": self.expected,
            "actual": self.actual,
            "passed": self.passed,
        }


@dataclass
class EvaluationResult:
    """Result of evaluating a set of conditions."""

    all_passed: bool
    total_conditions: int
    passed_count: int
    details: List[ConditionResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_conditions == 0:
            return 0.0
        return self.passed_count / self.total_conditions

    def to_dict(self) -> Dict[str, Any]:
        return {
            "all_passed": self.all_passed,
            "total_conditions": self.total_conditions,
            "passed_count": self.passed_count,
            "pass_rate": round(self.pass_rate, 4),
            "details": [d.to_dict() for d in self.details],
        }


class RuleEvaluator:
    """Evaluate structured buy/sell conditions against indicator data.

    Usage::

        evaluator = RuleEvaluator()
        result = evaluator.evaluate(
            conditions=[
                {"indicator": "rsi_12", "operator": "<", "value": 30},
                {"indicator": "kdj_signal", "operator": "==", "value": "golden_cross"},
            ],
            indicator_data=trend_result.to_dict(),
        )
        print(result.all_passed, result.pass_rate)
    """

    _OPERATORS = {
        "<": lambda a, b: a is not None and float(a) < float(b),
        "<=": lambda a, b: a is not None and float(a) <= float(b),
        ">": lambda a, b: a is not None and float(a) > float(b),
        ">=": lambda a, b: a is not None and float(a) >= float(b),
        "==": lambda a, b: a is not None and _eq(a, b),
        "!=": lambda a, b: a is not None and not _eq(a, b),
        "in": lambda a, b: (
            a is not None
            and isinstance(b, list)
            and str(_to_comparable(a)) in _to_str_list(b)
        ),
        "not_in": lambda a, b: (
            a is not None
            and isinstance(b, list)
            and str(_to_comparable(a)) not in _to_str_list(b)
        ),
        "between": lambda a, b: (
            a is not None
            and isinstance(b, list)
            and len(b) == 2
            and float(b[0]) <= float(a) <= float(b[1])
        ),
    }

    @classmethod
    def evaluate(
        cls,
        conditions: List[Dict[str, Any]],
        indicator_data: Dict[str, Any],
    ) -> EvaluationResult:
        """Evaluate all conditions against indicator data (AND logic).

        Args:
            conditions: List of condition dicts, each with
                ``indicator``, ``operator``, ``value``.
            indicator_data: Flat dict of indicator name → value.

        Returns:
            EvaluationResult with overall pass/fail and per-condition details.
        """
        if not conditions:
            return EvaluationResult(
                all_passed=False, total_conditions=0, passed_count=0,
            )

        results: List[ConditionResult] = []
        for cond in conditions:
            indicator = cond.get("indicator", "")
            operator = cond.get("operator", "")
            expected = cond.get("value")
            actual = indicator_data.get(indicator)

            op_fn = cls._OPERATORS.get(operator)
            if op_fn is None:
                logger.warning(
                    "Unknown operator '%s' for indicator '%s', treating as failed",
                    operator, indicator,
                )
                passed = False
            else:
                try:
                    passed = bool(op_fn(actual, expected))
                except (TypeError, ValueError) as exc:
                    logger.debug(
                        "Condition eval error: %s %s %s (actual=%s): %s",
                        indicator, operator, expected, actual, exc,
                    )
                    passed = False

            results.append(ConditionResult(
                indicator=indicator,
                operator=operator,
                expected=expected,
                actual=actual,
                passed=passed,
            ))

        passed_count = sum(1 for r in results if r.passed)
        all_passed = passed_count == len(results)

        return EvaluationResult(
            all_passed=all_passed,
            total_conditions=len(results),
            passed_count=passed_count,
            details=results,
        )

    @classmethod
    def evaluate_from_trend_result(
        cls,
        conditions: List[Dict[str, Any]],
        trend_result: Any,
    ) -> EvaluationResult:
        """Convenience: convert TrendAnalysisResult to dict, then evaluate.

        Args:
            conditions: List of condition dicts.
            trend_result: A ``TrendAnalysisResult`` instance with ``to_dict()`` method.

        Returns:
            EvaluationResult.
        """
        data = trend_result.to_dict()
        return cls.evaluate(conditions, data)
