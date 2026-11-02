"""Measure what at-least-once delivery costs a handler that is not idempotent.

Every queue worth using delivers at least once, which means it sometimes delivers twice.
Every client worth using retries, which means it sometimes applies twice. The two are the
same mechanism seen from opposite ends, and the damage is measurable.
"""

from retry_amplification.config import ConfigError, ScenarioConfig

__all__ = ["ScenarioConfig", "ConfigError"]
__version__ = "0.1.0"
