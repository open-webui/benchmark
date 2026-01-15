"""
Benchmark scenarios module.

Contains specific benchmark implementations for different Open WebUI features.
"""

from benchmark.scenarios.channels import ChannelAPIBenchmark
from benchmark.scenarios.chat import ChatAPIBenchmark

__all__ = [
    "ChannelAPIBenchmark",
    "ChatAPIBenchmark",
]
