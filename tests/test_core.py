"""
Tests for the benchmark core modules.
"""

import pytest
import asyncio
from datetime import datetime

from benchmark.core.config import (
    BenchmarkConfig,
    ConfigLoader,
    ComputeProfile,
    ResourceConfig,
    DockerConfig,
)
from benchmark.core.metrics import MetricsCollector, BenchmarkResult, TimingRecord


class TestMetricsCollector:
    """Tests for MetricsCollector."""
    
    def test_time_operation_success(self):
        """Test timing a successful operation."""
        collector = MetricsCollector()
        
        with collector.time_operation("test_op"):
            pass  # Simulate operation
        
        result = collector.get_result("test")
        assert result.total_requests == 1
        assert result.successful_requests == 1
        assert result.failed_requests == 0
    
    def test_time_operation_failure(self):
        """Test timing a failed operation."""
        collector = MetricsCollector()
        
        try:
            with collector.time_operation("test_op"):
                raise ValueError("Test error")
        except ValueError:
            pass
        
        result = collector.get_result("test")
        assert result.total_requests == 1
        assert result.successful_requests == 0
        assert result.failed_requests == 1
        assert "Test error" in result.errors
    
    def test_record_timing(self):
        """Test manual timing recording."""
        collector = MetricsCollector()
        
        collector.record_timing("op1", 100.0, success=True)
        collector.record_timing("op2", 200.0, success=True)
        collector.record_timing("op3", 300.0, success=False, error="Fail")
        
        result = collector.get_result("test")
        assert result.total_requests == 3
        assert result.successful_requests == 2
        assert result.failed_requests == 1
    
    def test_percentile_calculation(self):
        """Test percentile calculations."""
        collector = MetricsCollector()
        
        # Add 100 timings with known values
        for i in range(1, 101):
            collector.record_timing("op", float(i), success=True)
        
        result = collector.get_result("test")
        
        # P50 should be around 50
        assert 49 <= result.p50_response_time_ms <= 51
        
        # P95 should be around 95
        assert 94 <= result.p95_response_time_ms <= 96
        
        # P99 should be around 99
        assert 98 <= result.p99_response_time_ms <= 100
    
    def test_reset(self):
        """Test metrics reset."""
        collector = MetricsCollector()
        
        collector.record_timing("op", 100.0, success=True)
        collector.reset()
        
        result = collector.get_result("test")
        assert result.total_requests == 0


class TestBenchmarkResult:
    """Tests for BenchmarkResult."""
    
    def test_to_dict(self):
        """Test dictionary conversion."""
        result = BenchmarkResult(
            benchmark_name="Test",
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            avg_response_time_ms=150.5,
            concurrent_users=10,
        )
        
        d = result.to_dict()
        
        assert d["benchmark_name"] == "Test"
        assert d["total_requests"] == 100
        assert d["successful_requests"] == 95
        assert d["avg_response_time_ms"] == 150.5
    
    def test_to_json(self):
        """Test JSON conversion."""
        result = BenchmarkResult(
            benchmark_name="Test",
            total_requests=50,
        )
        
        json_str = result.to_json()
        
        assert "Test" in json_str
        assert "50" in json_str


class TestConfigLoader:
    """Tests for ConfigLoader."""
    
    def test_load_compute_profiles(self, tmp_path):
        """Test loading compute profiles from YAML."""
        # Create test config file
        config_dir = tmp_path / "config"
        config_dir.mkdir()
        
        profiles_yaml = """
profiles:
  test:
    name: "Test Profile"
    description: "A test profile"
    resources:
      cpus: 2.0
      memory: "4g"
      memory_swap: "4g"
      memory_reservation: "2g"
    docker:
      cpu_shares: 1024
      cpu_period: 100000
      cpu_quota: 200000
"""
        (config_dir / "compute_profiles.yaml").write_text(profiles_yaml)
        
        loader = ConfigLoader(config_dir)
        profiles = loader.load_compute_profiles()
        
        assert "test" in profiles
        assert profiles["test"].name == "Test Profile"
        assert profiles["test"].resources.cpus == 2.0


class TestTimingRecord:
    """Tests for TimingRecord."""
    
    def test_duration_calculation(self):
        """Test duration calculation."""
        record = TimingRecord(
            operation="test",
            start_time=0.0,
            end_time=0.5,
            success=True,
        )
        
        assert record.duration_seconds == 0.5
        assert record.duration_ms == 500.0
