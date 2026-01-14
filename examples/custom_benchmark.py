"""
Example showing how to create a custom benchmark.

This demonstrates extending the base benchmark class to create
new benchmark scenarios, using the auth entrypoint for consistent
authentication handling.
"""

import asyncio
import time
from typing import Optional

from benchmark.core.base import BaseBenchmark
from benchmark.core.config import BenchmarkConfig
from benchmark.core.metrics import BenchmarkResult
from benchmark.clients.http_client import OpenWebUIClient
from benchmark.auth import (
    ensure_admin_authenticated,
    AuthenticationError,
    ServiceNotReadyError,
)


class APILatencyBenchmark(BaseBenchmark):
    """
    Example custom benchmark that measures API endpoint latencies.
    
    This benchmark tests various API endpoints to establish baseline
    latency measurements.
    """
    
    name = "API Latency Baseline"
    description = "Measure baseline latency for key API endpoints"
    version = "1.0.0"
    
    # Endpoints to test
    ENDPOINTS = [
        ("GET", "/api/v1/channels/"),
        ("GET", "/api/v1/auths/"),
        ("GET", "/health"),
    ]
    
    def __init__(
        self,
        config: BenchmarkConfig,
        admin_client: Optional[OpenWebUIClient] = None,
    ):
        """
        Initialize the benchmark.
        
        Args:
            config: Benchmark configuration
            admin_client: Optional pre-authenticated admin client
        """
        super().__init__(config)
        self._client: Optional[OpenWebUIClient] = admin_client
        self._owns_client: bool = admin_client is None
    
    async def setup(self) -> None:
        """Set up the benchmark environment using auth entrypoint."""
        if self._client is None:
            try:
                self._client, auth_result = await ensure_admin_authenticated(
                    base_url=self.config.target_url,
                    timeout=self.config.request_timeout,
                )
                print(f"Authenticated as: {auth_result.user.email}")
                if auth_result.is_new_signup:
                    print("(Created new admin account)")
            except ServiceNotReadyError as e:
                raise RuntimeError(f"Service not ready: {e}")
            except AuthenticationError as e:
                raise RuntimeError(f"Authentication failed: {e}")
    
    async def run(self) -> BenchmarkResult:
        """Execute the benchmark."""
        self.metrics.start()
        
        # Number of requests per endpoint
        requests_per_endpoint = 100
        
        for method, endpoint in self.ENDPOINTS:
            for _ in range(requests_per_endpoint):
                start = time.time()
                success = True
                error = None
                
                try:
                    if method == "GET":
                        response = await self._client.client.get(
                            endpoint,
                            headers=self._client.headers,
                        )
                        response.raise_for_status()
                except Exception as e:
                    success = False
                    error = str(e)
                
                duration_ms = (time.time() - start) * 1000
                
                self.metrics.record_timing(
                    operation=f"{method} {endpoint}",
                    duration_ms=duration_ms,
                    success=success,
                    error=error,
                )
                
                # Small delay between requests
                await asyncio.sleep(0.01)
        
        self.metrics.stop()
        
        return self.metrics.get_result(
            benchmark_name=self.name,
            metadata={
                "endpoints_tested": len(self.ENDPOINTS),
                "requests_per_endpoint": requests_per_endpoint,
            },
        )
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self._client and self._owns_client:
            await self._client.close()


async def main():
    """Run the custom benchmark."""
    from benchmark.core.config import load_config
    from benchmark.core.runner import BenchmarkRunner
    
    config = load_config("default")
    
    runner = BenchmarkRunner(config=config)
    result = await runner.run_benchmark(APILatencyBenchmark)
    
    runner.display_final_summary()


if __name__ == "__main__":
    asyncio.run(main())
