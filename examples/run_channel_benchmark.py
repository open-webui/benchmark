"""
Example script demonstrating how to run the channel concurrency benchmark.

This script can be run directly or used as a reference for programmatic benchmark execution.
"""

import asyncio
from pathlib import Path

from benchmark.core.config import load_config
from benchmark.core.runner import BenchmarkRunner
from benchmark.scenarios.channels import ChannelConcurrencyBenchmark


async def main():
    """Run the channel concurrency benchmark with custom settings."""
    
    # Load configuration with the default compute profile
    config = load_config(
        profile_id="default",
        overrides={
            "target_url": "http://localhost:3000",
        }
    )
    
    # Customize channel benchmark settings
    config.channels.max_concurrent_users = 50  # Test up to 50 users
    config.channels.user_step_size = 10        # Increase by 10 users each level
    config.channels.sustain_time = 20          # Run each level for 20 seconds
    config.channels.message_frequency = 0.5    # 0.5 messages per second per user
    
    # Create benchmark runner
    runner = BenchmarkRunner(
        config=config,
        profile_id="default",
        output_dir=Path("./results"),
    )
    
    # Run the benchmark
    print("Starting Channel Concurrency Benchmark...")
    print(f"Target: {config.target_url}")
    print(f"Max users: {config.channels.max_concurrent_users}")
    print()
    
    result = await runner.run_benchmark(ChannelConcurrencyBenchmark)
    
    # Display results
    runner.display_final_summary()
    
    # Access specific metrics
    print(f"\n--- Benchmark Complete ---")
    print(f"Maximum sustainable users: {result.metadata.get('max_sustainable_users', 'N/A')}")
    print(f"Average response time: {result.avg_response_time_ms:.2f}ms")
    print(f"P95 response time: {result.p95_response_time_ms:.2f}ms")
    print(f"Error rate: {result.error_rate_percent:.2f}%")
    print(f"Passed: {'Yes' if result.passed else 'No'}")
    
    return result


if __name__ == "__main__":
    asyncio.run(main())
