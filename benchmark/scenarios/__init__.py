"""
Benchmark scenarios module.

Contains specific benchmark implementations for different Open WebUI features.
"""

from benchmark.scenarios.channels import ChannelConcurrencyBenchmark

__all__ = [
    "ChannelConcurrencyBenchmark",
]
