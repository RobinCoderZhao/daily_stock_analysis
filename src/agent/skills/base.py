# -*- coding: utf-8 -*-
"""
Strategy (Skill) base classes and SkillManager.

Strategies are pluggable trading analysis modules defined in **natural language**
(YAML files). Each strategy describes a common or custom trading pattern
(e.g., 龙头策略, 缩量回踩, 均线金叉) used for analysis and push notifications.

Users can write custom strategies by creating a YAML file — no Python code needed.
See ``strategies/README.md`` for the format specification.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# Built-in strategies directory (project_root/strategies/)
_BUILTIN_STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent.parent / "strategies"

# Strategy conflict matrix: pairs of strategies that may produce contradictory signals
_CONFLICT_MATRIX = {
    ("shrink_pullback", "volume_breakout"): "Volume direction conflict: shrink_pullback expects low volume, volume_breakout expects high volume",
    ("bull_trend", "bottom_volume"): "Trend direction conflict: bull_trend needs uptrend, bottom_volume needs downtrend reversal",
    ("box_oscillation", "volume_breakout"): "Structure conflict: box_oscillation expects range-bound, volume_breakout expects breakout",
}


@dataclass
class Skill:
    """A trading strategy that can be injected into the agent prompt.

    Each strategy represents a common or custom trading pattern used
    for stock analysis and push notifications. Strategies are typically
    loaded from YAML files written in natural language.

    Attributes:
        name: Unique strategy identifier (e.g., "dragon_head").
        display_name: Human-readable name (e.g., "龙头策略").
        description: Brief description of when to apply this strategy.
        instructions: Detailed natural language instructions injected into the system prompt.
        category: Strategy category — "trend" (趋势), "pattern" (形态), "reversal" (反转), "framework" (框架).
        core_rules: List of core trading rule numbers this strategy relates to (1-7).
        required_tools: List of tool names this strategy depends on.
        enabled: Whether this strategy is currently active.
        source: Origin of this strategy — "builtin" or file path of a custom YAML.
    """
    name: str
    display_name: str
    description: str
    instructions: str
    category: str = "trend"
    core_rules: List[int] = field(default_factory=list)
    required_tools: List[str] = field(default_factory=list)
    enabled: bool = False
    source: str = "builtin"
    # Confidence weight (0.0-1.0): how reliably an LLM can execute this strategy
    confidence_weight: float = 1.0
    # Applicable market conditions
    applicable_market: List[str] = field(default_factory=list)
    not_applicable_market: List[str] = field(default_factory=list)
    # Quantitative backtesting rules (Phase 1)
    # Contains buy_conditions, sell_conditions, holding_days, stop_loss_atr_multiple, etc.
    quantitative_rules: Optional[Dict] = None


def load_skill_from_yaml(filepath: Union[str, Path]) -> Skill:
    """Load a single Skill from a YAML file.

    The YAML file must contain at minimum: ``name``, ``display_name``,
    ``description``, and ``instructions``. All values are natural language text.

    Args:
        filepath: Path to the ``.yaml`` file.

    Returns:
        A ``Skill`` instance with ``enabled=False``.

    Raises:
        ValueError: If required fields are missing or the file is invalid.
        FileNotFoundError: If the file does not exist.
    """
    import yaml  # lazy import — only needed when loading strategies

    filepath = Path(filepath)
    if not filepath.exists():
        raise FileNotFoundError(f"Strategy file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"Invalid strategy file (expected YAML mapping): {filepath}")

    # Validate required fields
    required_fields = ["name", "display_name", "description", "instructions"]
    missing = [fld for fld in required_fields if not data.get(fld)]
    if missing:
        raise ValueError(
            f"Strategy file {filepath.name} missing required fields: {missing}"
        )

    return Skill(
        name=str(data["name"]).strip(),
        display_name=str(data["display_name"]).strip(),
        description=str(data["description"]).strip(),
        instructions=str(data["instructions"]).strip(),
        category=str(data.get("category", "trend")).strip(),
        core_rules=data.get("core_rules", []) or [],
        required_tools=data.get("required_tools", []) or [],
        enabled=False,
        source=str(filepath),
        confidence_weight=float(data.get("confidence_weight", 1.0)),
        applicable_market=data.get("applicable_market", []) or [],
        not_applicable_market=data.get("not_applicable_market", []) or [],
        quantitative_rules=data.get("quantitative_rules"),
    )


def load_skills_from_directory(directory: Union[str, Path]) -> List[Skill]:
    """Load all strategies from YAML files in a directory.

    Scans for ``*.yaml`` and ``*.yml`` files, sorted alphabetically.
    Skips files that fail to parse (logs a warning).

    Args:
        directory: Path to the directory containing YAML strategy files.

    Returns:
        List of ``Skill`` instances (all disabled by default).
    """
    directory = Path(directory)
    if not directory.is_dir():
        logger.warning(f"Strategy directory does not exist: {directory}")
        return []

    skills: List[Skill] = []
    yaml_files = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))

    for filepath in yaml_files:
        try:
            skill = load_skill_from_yaml(filepath)
            skills.append(skill)
            logger.debug(f"Loaded strategy from YAML: {skill.name} ({filepath.name})")
        except Exception as e:
            logger.warning(f"Failed to load strategy from {filepath.name}: {e}")

    return skills


class SkillManager:
    """Manages strategy plugins and generates combined prompt instructions.

    Supports loading strategies from:
    1. YAML files in the built-in ``strategies/`` directory
    2. YAML files in a user-specified custom directory
    3. Programmatic ``Skill`` instances (backward compatible)

    Usage::

        manager = SkillManager()
        # Load built-in + custom strategies from YAML
        manager.load_builtin_strategies()
        manager.load_custom_strategies("./my_strategies")
        # Or register programmatically
        manager.register(some_skill)
        # Activate and generate prompt
        manager.activate(["dragon_head", "shrink_pullback"])
        instructions = manager.get_skill_instructions()
    """

    def __init__(self):
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        """Register a skill (programmatic or YAML-loaded)."""
        self._skills[skill.name] = skill
        logger.debug(f"Registered strategy: {skill.name} ({skill.display_name})")

    def load_builtin_strategies(self) -> int:
        """Load all built-in strategies from the ``strategies/`` directory.

        Returns:
            Number of strategies loaded.
        """
        strategies_dir = _BUILTIN_STRATEGIES_DIR
        if not strategies_dir.is_dir():
            logger.warning(f"Built-in strategies directory not found: {strategies_dir}")
            return 0

        skills = load_skills_from_directory(strategies_dir)
        for skill in skills:
            skill.source = "builtin"
            self.register(skill)

        logger.info(f"Loaded {len(skills)} built-in strategies from {strategies_dir}")
        return len(skills)

    def load_custom_strategies(self, directory: Union[str, Path, None]) -> int:
        """Load custom strategies from a user-specified directory.

        Custom strategies override built-in ones if names conflict.

        Args:
            directory: Path to the custom strategies directory.
                       If None or empty, does nothing.

        Returns:
            Number of strategies loaded.
        """
        if not directory:
            return 0

        directory = Path(directory)
        if not directory.is_dir():
            logger.warning(f"Custom strategy directory does not exist: {directory}")
            return 0

        skills = load_skills_from_directory(directory)
        for skill in skills:
            skill.source = str(directory / f"{skill.name}.yaml")
            if skill.name in self._skills:
                logger.info(
                    f"Custom strategy '{skill.name}' overrides built-in"
                )
            self.register(skill)

        logger.info(f"Loaded {len(skills)} custom strategies from {directory}")
        return len(skills)

    def get(self, name: str) -> Optional[Skill]:
        """Get a skill by name."""
        return self._skills.get(name)

    def list_skills(self) -> List[Skill]:
        """List all registered skills."""
        return list(self._skills.values())

    def list_active_skills(self) -> List[Skill]:
        """List only active (enabled) skills."""
        return [s for s in self._skills.values() if s.enabled]

    def activate(self, skill_names: List[str]) -> None:
        """Activate specific skills by name. Deactivate all others.

        Args:
            skill_names: List of skill names to activate.
                         If ["all"], activate everything.
        """
        if skill_names == ["all"] or "all" in skill_names:
            for s in self._skills.values():
                s.enabled = True
            logger.info(f"Activated all {len(self._skills)} strategies")
            return

        for s in self._skills.values():
            s.enabled = s.name in skill_names

        activated = [s.name for s in self._skills.values() if s.enabled]
        logger.info(f"Activated strategies: {activated}")

        # Check for conflicts among activated strategies
        conflicts = self.check_conflicts()
        for conflict_msg in conflicts:
            logger.warning(f"Strategy conflict: {conflict_msg}")

    def check_conflicts(self) -> List[str]:
        """Check for conflicts among active strategies.

        Returns:
            List of conflict warning messages (empty if no conflicts).
        """
        active_names = {s.name for s in self._skills.values() if s.enabled}
        conflicts = []
        for (a, b), reason in _CONFLICT_MATRIX.items():
            if a in active_names and b in active_names:
                conflicts.append(f"{a} ↔ {b}: {reason}")
        return conflicts

    def get_skill_instructions(self) -> str:
        """Generate combined instruction text for all active skills.

        Returns a formatted string ready to be injected into the agent
        system prompt, organized by category.
        """
        active = self.list_active_skills()
        if not active:
            return ""

        # Group by category
        categories = {"trend": "趋势", "pattern": "形态", "reversal": "反转", "framework": "框架"}
        grouped: Dict[str, List[Skill]] = {}
        for skill in active:
            cat = skill.category or "trend"
            grouped.setdefault(cat, []).append(skill)

        parts = []
        idx = 1
        # Render known categories in fixed order, then any remaining custom categories
        ordered_keys = ["trend", "pattern", "reversal", "framework"]
        for cat_key in ordered_keys + [k for k in grouped if k not in ordered_keys]:
            skills_in_cat = grouped.get(cat_key, [])
            if not skills_in_cat:
                continue
            cat_label = categories.get(cat_key, cat_key)
            parts.append(f"#### {cat_label}类策略\n")
            for skill in skills_in_cat:
                rules_ref = ""
                if skill.core_rules:
                    rules_ref = f"（关联核心理念：第{'、'.join(str(r) for r in skill.core_rules)}条）"
                # Confidence hint for the LLM
                confidence_note = ""
                if skill.confidence_weight < 0.7:
                    confidence_note = f"\n> ⚠️ 此策略置信度较低({skill.confidence_weight})，建议结合其他策略交叉验证再做判断。"
                elif skill.confidence_weight < 0.9:
                    confidence_note = f"\n> ℹ️ 此策略置信度中等({skill.confidence_weight})，建议参考但不作为唯一决策依据。"
                parts.append(
                    f"### 策略 {idx}: {skill.display_name} {rules_ref}\n\n"
                    f"**适用场景**: {skill.description}\n"
                    f"{confidence_note}\n"
                    f"{skill.instructions}\n"
                )
                idx += 1

        return "\n".join(parts)

    def get_required_tools(self) -> List[str]:
        """Get all tool names required by active skills."""
        tools: set = set()
        for s in self.list_active_skills():
            tools.update(s.required_tools)
        return list(tools)

    def match_strategies_for_market(self, market_condition: str) -> List[str]:
        """Return strategy names suitable for the given market condition.

        This enables proactive strategy matching: instead of injecting all
        active strategies into the prompt, only inject those whose
        ``applicable_market`` includes the current condition.

        Args:
            market_condition: One of "trend", "oscillation", "reversal", "crash".

        Returns:
            List of strategy names that are applicable.
            If no explicit matches, returns all active strategy names (fallback).
        """
        active = self.list_active_skills()
        if not active:
            return []

        matched = []
        for skill in active:
            # Skip if strategy explicitly excludes this market
            if market_condition in skill.not_applicable_market:
                continue
            # Include if applicable_market is empty (compatible with all) or matches
            if not skill.applicable_market or market_condition in skill.applicable_market:
                matched.append(skill.name)

        # Fallback: if filtering removed everything, return all active
        if not matched:
            matched = [s.name for s in active]
            logger.info(f"No strategies matched market '{market_condition}', using all {len(matched)} active strategies")

        return matched
