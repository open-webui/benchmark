"""
Metrics collection and result management for benchmarks.

Provides utilities for recording timing information, calculating statistics,
and generating benchmark reports.
"""

import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import json
import csv
from pathlib import Path


@dataclass
class TimingRecord:
    """A single timing record for a request or operation."""
    operation: str
    start_time: float
    end_time: float
    success: bool
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_ms(self) -> float:
        """Get duration in milliseconds."""
        return (self.end_time - self.start_time) * 1000
    
    @property
    def duration_seconds(self) -> float:
        """Get duration in seconds."""
        return self.end_time - self.start_time


@dataclass
class BenchmarkResult:
    """Results from a benchmark run."""
    benchmark_name: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    # Request counts
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    
    # Timing statistics (milliseconds)
    avg_response_time_ms: float = 0.0
    min_response_time_ms: float = 0.0
    max_response_time_ms: float = 0.0
    p50_response_time_ms: float = 0.0
    p95_response_time_ms: float = 0.0
    p99_response_time_ms: float = 0.0
    
    # Throughput
    requests_per_second: float = 0.0
    total_duration_seconds: float = 0.0
    
    # Error information
    error_rate_percent: float = 0.0
    errors: List[str] = field(default_factory=list)
    
    # Validation
    passed: bool = False
    iterations: int = 1
    
    # Resource metrics
    peak_cpu_percent: float = 0.0
    peak_memory_mb: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_memory_mb: float = 0.0
    
    # Additional data
    metadata: Dict[str, Any] = field(default_factory=dict)
    detailed_timings: List[TimingRecord] = field(default_factory=list)
    
    # Concurrent users (for channel benchmarks)
    concurrent_users: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert result to dictionary."""
        return {
            "benchmark_name": self.benchmark_name,
            "timestamp": self.timestamp.isoformat(),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "avg_response_time_ms": round(self.avg_response_time_ms, 2),
            "min_response_time_ms": round(self.min_response_time_ms, 2),
            "max_response_time_ms": round(self.max_response_time_ms, 2),
            "p50_response_time_ms": round(self.p50_response_time_ms, 2),
            "p95_response_time_ms": round(self.p95_response_time_ms, 2),
            "p99_response_time_ms": round(self.p99_response_time_ms, 2),
            "requests_per_second": round(self.requests_per_second, 2),
            "total_duration_seconds": round(self.total_duration_seconds, 2),
            "error_rate_percent": round(self.error_rate_percent, 2),
            "errors": self.errors[:10],  # Limit to first 10 errors
            "passed": self.passed,
            "iterations": self.iterations,
            "concurrent_users": self.concurrent_users,
            "peak_cpu_percent": round(self.peak_cpu_percent, 2),
            "peak_memory_mb": round(self.peak_memory_mb, 2),
            "avg_cpu_percent": round(self.avg_cpu_percent, 2),
            "avg_memory_mb": round(self.avg_memory_mb, 2),
            "metadata": self.metadata,
        }
    
    def to_json(self) -> str:
        """Convert result to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class MetricsCollector:
    """
    Collects and calculates metrics during benchmark execution.
    
    Usage:
        collector = MetricsCollector()
        
        # Record individual timings
        with collector.time_operation("api_call"):
            response = await make_api_call()
        
        # Get results
        result = collector.get_result("my_benchmark")
    """
    
    def __init__(self):
        """Initialize the metrics collector."""
        self._timings: List[TimingRecord] = []
        self._start_time: Optional[float] = None
        self._end_time: Optional[float] = None
        self._resource_samples: List[Dict[str, float]] = []
        
    def start(self) -> None:
        """Start the metrics collection timer."""
        self._start_time = time.time()
        
    def stop(self) -> None:
        """Stop the metrics collection timer."""
        self._end_time = time.time()
    
    @contextmanager
    def time_operation(self, operation: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Context manager to time an operation.
        
        Args:
            operation: Name of the operation being timed
            metadata: Optional metadata to attach to the timing record
            
        Yields:
            The timing record (can be modified to set success/error)
        """
        record = TimingRecord(
            operation=operation,
            start_time=time.time(),
            end_time=0,
            success=True,
            metadata=metadata or {},
        )
        
        try:
            yield record
            record.success = True
        except Exception as e:
            record.success = False
            record.error = str(e)
            raise
        finally:
            record.end_time = time.time()
            self._timings.append(record)
    
    def record_timing(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Manually record a timing.
        
        Args:
            operation: Name of the operation
            duration_ms: Duration in milliseconds
            success: Whether the operation was successful
            error: Error message if failed
            metadata: Optional metadata
        """
        now = time.time()
        duration_seconds = duration_ms / 1000
        
        record = TimingRecord(
            operation=operation,
            start_time=now - duration_seconds,
            end_time=now,
            success=success,
            error=error,
            metadata=metadata or {},
        )
        self._timings.append(record)
    
    def record_resource_sample(self, cpu_percent: float, memory_mb: float) -> None:
        """
        Record a resource usage sample.
        
        Args:
            cpu_percent: CPU usage percentage
            memory_mb: Memory usage in MB
        """
        self._resource_samples.append({
            "timestamp": time.time(),
            "cpu_percent": cpu_percent,
            "memory_mb": memory_mb,
        })
    
    def get_result(
        self, 
        benchmark_name: str,
        concurrent_users: int = 0,
        include_detailed_timings: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> BenchmarkResult:
        """
        Calculate and return benchmark results.
        
        Args:
            benchmark_name: Name of the benchmark
            concurrent_users: Number of concurrent users tested
            include_detailed_timings: Whether to include all timing records
            metadata: Additional metadata to include
            
        Returns:
            BenchmarkResult with calculated statistics
        """
        result = BenchmarkResult(
            benchmark_name=benchmark_name,
            concurrent_users=concurrent_users,
            metadata=metadata or {},
        )
        
        if not self._timings:
            return result
        
        # Calculate request counts
        result.total_requests = len(self._timings)
        result.successful_requests = sum(1 for t in self._timings if t.success)
        result.failed_requests = result.total_requests - result.successful_requests
        
        # Get durations in milliseconds
        durations = [t.duration_ms for t in self._timings]
        successful_durations = [t.duration_ms for t in self._timings if t.success]
        
        if successful_durations:
            # Calculate timing statistics on successful requests
            result.avg_response_time_ms = statistics.mean(successful_durations)
            result.min_response_time_ms = min(successful_durations)
            result.max_response_time_ms = max(successful_durations)
            
            sorted_durations = sorted(successful_durations)
            result.p50_response_time_ms = self._percentile(sorted_durations, 50)
            result.p95_response_time_ms = self._percentile(sorted_durations, 95)
            result.p99_response_time_ms = self._percentile(sorted_durations, 99)
        
        # Calculate duration
        if self._start_time and self._end_time:
            result.total_duration_seconds = self._end_time - self._start_time
        else:
            # Fall back to timing record range
            result.total_duration_seconds = (
                max(t.end_time for t in self._timings) - 
                min(t.start_time for t in self._timings)
            )
        
        # Calculate throughput
        if result.total_duration_seconds > 0:
            result.requests_per_second = result.total_requests / result.total_duration_seconds
        
        # Calculate error rate
        if result.total_requests > 0:
            result.error_rate_percent = (result.failed_requests / result.total_requests) * 100
        
        # Collect unique errors
        result.errors = list(set(
            t.error for t in self._timings 
            if t.error is not None
        ))
        
        # Calculate resource metrics
        if self._resource_samples:
            cpu_values = [s["cpu_percent"] for s in self._resource_samples]
            memory_values = [s["memory_mb"] for s in self._resource_samples]
            
            result.peak_cpu_percent = max(cpu_values)
            result.peak_memory_mb = max(memory_values)
            result.avg_cpu_percent = statistics.mean(cpu_values)
            result.avg_memory_mb = statistics.mean(memory_values)
        
        # Include detailed timings if requested
        if include_detailed_timings:
            result.detailed_timings = self._timings.copy()
        
        return result
    
    def _percentile(self, sorted_data: List[float], percentile: float) -> float:
        """Calculate percentile value from sorted data."""
        if not sorted_data:
            return 0.0
        
        k = (len(sorted_data) - 1) * (percentile / 100)
        f = int(k)
        c = f + 1 if f + 1 < len(sorted_data) else f
        
        if f == c:
            return sorted_data[f]
        
        return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)
    
    def reset(self) -> None:
        """Reset all collected metrics."""
        self._timings.clear()
        self._resource_samples.clear()
        self._start_time = None
        self._end_time = None


class ResultsWriter:
    """Writes benchmark results to various formats."""
    
    def __init__(self, output_dir: Path):
        """
        Initialize the results writer.
        
        Args:
            output_dir: Directory to write results to
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def write_json(self, result: BenchmarkResult, filename: Optional[str] = None) -> Path:
        """
        Write result to JSON file.
        
        Args:
            result: Benchmark result to write
            filename: Optional filename (default: benchmark_name_timestamp.json)
            
        Returns:
            Path to written file
        """
        if filename is None:
            timestamp = result.timestamp.strftime("%Y%m%d_%H%M%S")
            filename = f"{result.benchmark_name.replace(' ', '_').lower()}_{timestamp}.json"
        
        filepath = self.output_dir / filename
        
        with open(filepath, 'w') as f:
            f.write(result.to_json())
        
        return filepath
    
    def write_csv(
        self, 
        results: List[BenchmarkResult], 
        filename: str = "benchmark_results.csv"
    ) -> Path:
        """
        Write multiple results to CSV file.
        
        Args:
            results: List of benchmark results
            filename: Output filename
            
        Returns:
            Path to written file
        """
        filepath = self.output_dir / filename
        
        fieldnames = [
            "benchmark_name", "timestamp", "concurrent_users",
            "total_requests", "successful_requests", "failed_requests",
            "avg_response_time_ms", "min_response_time_ms", "max_response_time_ms",
            "p50_response_time_ms", "p95_response_time_ms", "p99_response_time_ms",
            "requests_per_second", "error_rate_percent", "passed",
            "peak_cpu_percent", "peak_memory_mb",
        ]
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
            writer.writeheader()
            
            for result in results:
                row = result.to_dict()
                row["timestamp"] = result.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow(row)
        
        return filepath
    
    def write_summary(self, results: List[BenchmarkResult], filename: str = "summary.txt") -> Path:
        """
        Write a human-readable summary of results.
        
        Args:
            results: List of benchmark results
            filename: Output filename
            
        Returns:
            Path to written file
        """
        filepath = self.output_dir / filename
        
        lines = [
            "=" * 60,
            "BENCHMARK RESULTS SUMMARY",
            "=" * 60,
            "",
        ]
        
        for result in results:
            lines.extend([
                f"Benchmark: {result.benchmark_name}",
                f"  Concurrent Users: {result.concurrent_users}",
                f"  Total Requests: {result.total_requests}",
                f"  Success Rate: {100 - result.error_rate_percent:.1f}%",
                f"  Avg Response Time: {result.avg_response_time_ms:.2f}ms",
                f"  P95 Response Time: {result.p95_response_time_ms:.2f}ms",
                f"  Requests/sec: {result.requests_per_second:.2f}",
                f"  Status: {'PASSED' if result.passed else 'FAILED'}",
                "",
            ])
        
        lines.extend([
            "=" * 60,
        ])
        
        with open(filepath, 'w') as f:
            f.write('\n'.join(lines))
        
        return filepath
