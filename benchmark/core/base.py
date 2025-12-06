"""
Base benchmark class that all benchmark implementations should extend.

Provides common functionality for benchmark setup, execution, and teardown.
"""

import asyncio
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List, Callable
from datetime import datetime

from benchmark.core.config import BenchmarkConfig
from benchmark.core.metrics import MetricsCollector, BenchmarkResult


@dataclass
class BenchmarkContext:
    """Context object passed to benchmark methods."""
    config: BenchmarkConfig
    metrics: MetricsCollector
    iteration: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    user_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        if self.start_time is None:
            return 0.0
        end = self.end_time or time.time()
        return end - self.start_time


class BaseBenchmark(ABC):
    """
    Base class for all benchmarks.
    
    Subclasses should implement:
    - setup(): Prepare the benchmark environment
    - run(): Execute the actual benchmark
    - teardown(): Clean up after the benchmark
    - validate_result(): Validate the benchmark passed thresholds
    """
    
    name: str = "Base Benchmark"
    description: str = "Base benchmark class"
    version: str = "1.0.0"
    
    def __init__(self, config: BenchmarkConfig):
        """
        Initialize the benchmark.
        
        Args:
            config: Benchmark configuration
        """
        self.config = config
        self.metrics = MetricsCollector()
        self._context: Optional[BenchmarkContext] = None
        self._setup_complete = False
        self._teardown_complete = False
        
    @property
    def context(self) -> BenchmarkContext:
        """Get the current benchmark context."""
        if self._context is None:
            self._context = BenchmarkContext(
                config=self.config,
                metrics=self.metrics,
            )
        return self._context
    
    @abstractmethod
    async def setup(self) -> None:
        """
        Set up the benchmark environment.
        
        This method should:
        - Create necessary test data (users, channels, etc.)
        - Establish connections
        - Verify the target system is ready
        
        Raises:
            Exception: If setup fails
        """
        pass
    
    @abstractmethod
    async def run(self) -> BenchmarkResult:
        """
        Execute the benchmark.
        
        This method should:
        - Execute the benchmark workload
        - Record metrics using self.metrics
        - Return the benchmark result
        
        Returns:
            BenchmarkResult with collected metrics
        """
        pass
    
    @abstractmethod
    async def teardown(self) -> None:
        """
        Clean up after the benchmark.
        
        This method should:
        - Clean up test data
        - Close connections
        - Release resources
        """
        pass
    
    def validate_result(self, result: BenchmarkResult) -> bool:
        """
        Validate that the benchmark result meets thresholds.
        
        Args:
            result: The benchmark result to validate
            
        Returns:
            True if all thresholds are met, False otherwise
        """
        thresholds = self.config.thresholds
        
        # Check response time threshold
        if result.avg_response_time_ms > thresholds.max_response_time_ms:
            return False
        
        # Check P95 response time threshold
        if result.p95_response_time_ms > thresholds.max_p95_response_time_ms:
            return False
        
        # Check error rate threshold
        if result.error_rate_percent > thresholds.max_error_rate_percent:
            return False
        
        # Check requests per second threshold
        if result.requests_per_second < thresholds.min_requests_per_second:
            return False
        
        return True
    
    async def warmup(self) -> None:
        """
        Execute warmup requests before the main benchmark.
        
        Override this method to customize warmup behavior.
        """
        pass
    
    async def cooldown(self) -> None:
        """
        Execute cooldown period after the benchmark.
        
        Default implementation waits for configured cooldown time.
        """
        await asyncio.sleep(self.config.cooldown_seconds)
    
    async def execute(self) -> BenchmarkResult:
        """
        Execute the full benchmark lifecycle.
        
        This method orchestrates:
        1. Setup
        2. Warmup
        3. Run (multiple iterations if configured)
        4. Cooldown
        5. Teardown
        
        Returns:
            Combined BenchmarkResult from all iterations
        """
        try:
            # Setup
            await self.setup()
            self._setup_complete = True
            
            # Warmup
            if self.config.warmup_requests > 0:
                await self.warmup()
            
            # Run benchmark iterations
            results: List[BenchmarkResult] = []
            
            for iteration in range(self.config.iterations):
                self.context.iteration = iteration + 1
                self.context.start_time = time.time()
                
                result = await self.run()
                
                self.context.end_time = time.time()
                results.append(result)
                
                # Cooldown between iterations (except last)
                if iteration < self.config.iterations - 1:
                    await self.cooldown()
            
            # Combine results from all iterations
            combined_result = self._combine_results(results)
            combined_result.passed = self.validate_result(combined_result)
            
            return combined_result
            
        finally:
            # Always attempt teardown
            if self._setup_complete and not self._teardown_complete:
                await self.teardown()
                self._teardown_complete = True
    
    def _combine_results(self, results: List[BenchmarkResult]) -> BenchmarkResult:
        """
        Combine multiple iteration results into a single result.
        
        Args:
            results: List of results from each iteration
            
        Returns:
            Combined BenchmarkResult
        """
        if not results:
            return BenchmarkResult(
                benchmark_name=self.name,
                timestamp=datetime.utcnow(),
            )
        
        # Use first result as base
        combined = results[0]
        
        if len(results) == 1:
            return combined
        
        # Average numeric metrics across iterations
        combined.total_requests = sum(r.total_requests for r in results)
        combined.successful_requests = sum(r.successful_requests for r in results)
        combined.failed_requests = sum(r.failed_requests for r in results)
        combined.total_duration_seconds = sum(r.total_duration_seconds for r in results)
        
        # Average response times
        combined.avg_response_time_ms = sum(r.avg_response_time_ms for r in results) / len(results)
        combined.min_response_time_ms = min(r.min_response_time_ms for r in results)
        combined.max_response_time_ms = max(r.max_response_time_ms for r in results)
        combined.p50_response_time_ms = sum(r.p50_response_time_ms for r in results) / len(results)
        combined.p95_response_time_ms = sum(r.p95_response_time_ms for r in results) / len(results)
        combined.p99_response_time_ms = sum(r.p99_response_time_ms for r in results) / len(results)
        
        # Recalculate derived metrics
        if combined.total_requests > 0:
            combined.error_rate_percent = (combined.failed_requests / combined.total_requests) * 100
        
        if combined.total_duration_seconds > 0:
            combined.requests_per_second = combined.total_requests / combined.total_duration_seconds
        
        combined.iterations = len(results)
        
        return combined
    
    def get_metadata(self) -> Dict[str, Any]:
        """
        Get benchmark metadata.
        
        Returns:
            Dictionary containing benchmark metadata
        """
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "config": {
                "target_url": self.config.target_url,
                "iterations": self.config.iterations,
                "compute_profile": self.config.compute_profile.name if self.config.compute_profile else None,
            }
        }
