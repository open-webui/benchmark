"""
Example script demonstrating how to run the channel concurrency benchmark.

This script shows two approaches:
1. Let the benchmark handle authentication internally (simple)
2. Pre-authenticate using the entrypoint and pass the client (explicit)

The explicit approach is useful when you want to:
- Validate authentication before starting benchmarks
- Share one authenticated session across multiple benchmarks
- Handle auth errors separately from benchmark errors
"""

import asyncio
from pathlib import Path

from benchmark.core.config import load_config
from benchmark.core.runner import BenchmarkRunner
from benchmark.scenarios.channels import ChannelConcurrencyBenchmark
from benchmark.auth import ensure_admin_authenticated


async def main_simple():
    """
    Run benchmark with internal authentication (simple approach).
    
    The benchmark will handle authentication using credentials from
    environment variables (ADMIN_USER_EMAIL, ADMIN_USER_PASSWORD).
    """
    # Load configuration with the default compute profile
    config = load_config(
        profile_id="default",
        overrides={
            "target_url": "http://localhost:3000",
        }
    )
    
    # Customize channel benchmark settings
    config.channels.max_concurrent_users = 50
    config.channels.user_step_size = 10
    config.channels.sustain_time = 20
    config.channels.message_frequency = 0.5
    
    # Create benchmark runner
    runner = BenchmarkRunner(
        config=config,
        profile_id="default",
        output_dir=Path("./results"),
    )
    
    # Run the benchmark (handles auth internally)
    print("Starting Channel Concurrency Benchmark...")
    print(f"Target: {config.target_url}")
    print(f"Max users: {config.channels.max_concurrent_users}")
    print()
    
    result = await runner.run_benchmark(ChannelConcurrencyBenchmark)
    
    # Display results
    runner.display_final_summary()
    
    return result


async def main_explicit():
    """
    Run benchmark with explicit pre-authentication (recommended approach).
    
    This approach uses the auth entrypoint to authenticate before
    creating the benchmark, giving you more control over error handling.
    """
    # Load configuration
    config = load_config(
        profile_id="default",
        overrides={
            "target_url": "http://localhost:3000",
        }
    )
    
    config.channels.max_concurrent_users = 50
    config.channels.user_step_size = 10
    config.channels.sustain_time = 20
    config.channels.message_frequency = 0.5
    
    # Pre-authenticate using the entrypoint
    print("Authenticating...")
    client, auth_result = await ensure_admin_authenticated(
        base_url=config.target_url,
        timeout=config.request_timeout,
    )
    
    print(f"Authenticated as: {auth_result.user.email} (role: {auth_result.user.role})")
    if auth_result.is_new_signup:
        print("Note: Created new admin account (first run)")
    print()
    
    try:
        # Create benchmark runner
        runner = BenchmarkRunner(
            config=config,
            profile_id="default",
            output_dir=Path("./results"),
        )
        
        # Create benchmark with pre-authenticated client
        benchmark = ChannelConcurrencyBenchmark(config, admin_client=client)
        
        # Run the benchmark
        print("Starting Channel Concurrency Benchmark...")
        print(f"Target: {config.target_url}")
        print(f"Max users: {config.channels.max_concurrent_users}")
        print()
        
        result = await runner.run_benchmark(benchmark)
        
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
    finally:
        # Clean up the client we created
        await client.close()


if __name__ == "__main__":
    # Use the explicit approach by default
    asyncio.run(main_explicit())
