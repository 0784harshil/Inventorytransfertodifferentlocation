"""Recommendation / stock-health rule thresholds.

Defaults match the original hardcoded behavior:
  low_stock_at     = 5   (dest is low when stock <= this)
  surplus_above    = 20  (source has surplus when stock > this)
  target_stock     = 10  (aim to bring destination up to this)
"""
from __future__ import annotations

from dataclasses import dataclass
import logging


DEFAULT_LOW_STOCK_AT = 5.0
DEFAULT_SURPLUS_ABOVE = 20.0
DEFAULT_TARGET_STOCK = 10.0


@dataclass
class RecommendationRules:
    low_stock_at: float = DEFAULT_LOW_STOCK_AT
    surplus_above: float = DEFAULT_SURPLUS_ABOVE
    target_stock: float = DEFAULT_TARGET_STOCK

    def validate(self) -> None:
        # Negative thresholds are allowed (e.g. dest already below zero stock).
        if self.target_stock < self.low_stock_at:
            raise ValueError(
                "Target stock should be greater than or equal to the low-stock threshold."
            )
        if self.surplus_above < self.target_stock:
            raise ValueError(
                "Surplus threshold should be greater than or equal to the target stock."
            )

    def copy(self) -> "RecommendationRules":
        return RecommendationRules(
            low_stock_at=self.low_stock_at,
            surplus_above=self.surplus_above,
            target_stock=self.target_stock,
        )

    def describe(self) -> str:
        return (
            f"Dest <= {self.low_stock_at:g}, "
            f"Source > {self.surplus_above:g}, "
            f"Target {self.target_stock:g}"
        )


def load_rules_from_config(config) -> RecommendationRules:
    """Load rules from [RECOMMENDATION_RULES]; fall back to defaults if missing."""
    section = "RECOMMENDATION_RULES"
    rules = RecommendationRules()
    if config is None or section not in config:
        return rules
    try:
        rules.low_stock_at = float(
            config.get(section, "low_stock_at", fallback=str(DEFAULT_LOW_STOCK_AT))
        )
        rules.surplus_above = float(
            config.get(section, "surplus_above", fallback=str(DEFAULT_SURPLUS_ABOVE))
        )
        rules.target_stock = float(
            config.get(section, "target_stock", fallback=str(DEFAULT_TARGET_STOCK))
        )
        rules.validate()
    except Exception as e:
        logging.warning(f"Invalid recommendation rules in config; using defaults. ({e})")
        return RecommendationRules()
    return rules


def save_rules_to_config(config, config_path, rules: RecommendationRules) -> None:
    """Persist rules into config.ini under [RECOMMENDATION_RULES]."""
    rules.validate()
    section = "RECOMMENDATION_RULES"
    if section not in config:
        config.add_section(section)
    config[section]["low_stock_at"] = str(rules.low_stock_at)
    config[section]["surplus_above"] = str(rules.surplus_above)
    config[section]["target_stock"] = str(rules.target_stock)
    with open(config_path, "w", encoding="utf-8") as f:
        config.write(f)
    logging.info(
        f"Recommendation rules saved to {config_path}: {rules.describe()}"
    )
