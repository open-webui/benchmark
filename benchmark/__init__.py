"""
Open WebUI Benchmark Suite

A comprehensive benchmarking framework for testing Open WebUI performance
under various load conditions.
"""

__version__ = "0.1.0"
__author__ = "Open WebUI Benchmark Team"

from benchmark.core.runner import BenchmarkRunner
from benchmark.core.config import BenchmarkConfig
from benchmark.core.metrics import MetricsCollector

__all__ = [
    "BenchmarkRunner",
    "BenchmarkConfig", 
    "MetricsCollector",
]
