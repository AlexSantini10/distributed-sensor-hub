"""Collect built-in sensor providers and their shared base implementation."""

from .base_sensor import BaseSensor
from .boolean_sensor import BooleanSensor
from .categorical_sensor import CategoricalSensor
from .incremental_sensor import IncrementalSensor
from .noise_sensor import NoiseSensor
from .numeric_sensor import NumericSensor
from .spike_sensor import SpikeSensor
from .trend_sensor import TrendSensor
from .wave_sensor import WaveSensor

__all__ = [
    "BaseSensor",
    "BooleanSensor",
    "CategoricalSensor",
    "IncrementalSensor",
    "NoiseSensor",
    "NumericSensor",
    "SpikeSensor",
    "TrendSensor",
    "WaveSensor",
]
