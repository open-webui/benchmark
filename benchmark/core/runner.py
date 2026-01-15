"""
Benchmark runner - orchestrates benchmark execution.

Handles Docker container management, benchmark lifecycle, and result collection.
"""

import asyncio
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Type
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich.panel import Panel

from benchmark.core.config import BenchmarkConfig, ConfigLoader, load_config
from benchmark.core.base import BaseBenchmark
from benchmark.core.metrics import BenchmarkResult, ResultsWriter


console = Console()


class BenchmarkRunner:
    """
    Orchestrates benchmark execution.
    
    Handles:
    - Loading configuration
    - Managing Docker containers with resource constraints
    - Running benchmarks
    - Collecting and reporting results
    """
    
    def __init__(
        self,
        config: Optional[BenchmarkConfig] = None,
        profile_id: str = "default",
        output_dir: Optional[Path] = None,
    ):
        """
        Initialize the benchmark runner.
        
        Args:
            config: Optional pre-loaded configuration
            profile_id: Compute profile to use
            output_dir: Directory for benchmark results
        """
        self.config = config or load_config(profile_id)
        self.profile_id = profile_id
        
        # Set up output directory
        if output_dir is None:
            output_dir = Path(__file__).parent.parent.parent / "results"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.results_writer = ResultsWriter(self.output_dir)
        self._benchmarks: Dict[str, Type[BaseBenchmark]] = {}
        self._results: List[BenchmarkResult] = []
        
    def register_benchmark(self, benchmark_class: Type[BaseBenchmark]) -> None:
        """
        Register a benchmark class for execution.
        
        Args:
            benchmark_class: The benchmark class to register
        """
        self._benchmarks[benchmark_class.name] = benchmark_class
    
    async def run_benchmark(
        self,
        benchmark_class: Type[BaseBenchmark],
        **kwargs: Any,
    ) -> BenchmarkResult:
        """
        Run a single benchmark.
        
        Args:
            benchmark_class: The benchmark class to run
            **kwargs: Additional arguments to pass to the benchmark
            
        Returns:
            BenchmarkResult from the benchmark
        """
        console.print(Panel(
            f"[bold blue]Running: {benchmark_class.name}[/bold blue]\n"
            f"[dim]{benchmark_class.description}[/dim]",
            title="Benchmark",
            border_style="blue",
        ))
        
        # Create benchmark instance
        benchmark = benchmark_class(self.config)
        
        try:
            # Execute benchmark (benchmark manages its own progress display)
            result = await benchmark.execute()
            
            # Store result
            self._results.append(result)
            
        except Exception as e:
            console.print(f"[red]Error running benchmark: {e}[/red]")
            raise
        
        # Display result summary
        self._display_result_summary(result)
        
        # Write results to file
        self._write_results([result])
        
        return result
    
    async def run_all(self) -> List[BenchmarkResult]:
        """
        Run all registered benchmarks.
        
        Returns:
            List of BenchmarkResult from all benchmarks
        """
        if not self._benchmarks:
            console.print("[yellow]No benchmarks registered![/yellow]")
            return []
        
        console.print(Panel(
            f"[bold green]Running {len(self._benchmarks)} benchmark(s)[/bold green]\n"
            f"Profile: {self.profile_id}\n"
            f"Target: {self.config.target_url}",
            title="Benchmark Suite",
            border_style="green",
        ))
        
        results = []
        for name, benchmark_class in self._benchmarks.items():
            try:
                result = await self.run_benchmark(benchmark_class)
                results.append(result)
            except Exception as e:
                console.print(f"[red]Benchmark '{name}' failed: {e}[/red]")
        
        # Write all results
        self._write_results(results)
        
        return results
    
    def _display_result_summary(self, result: BenchmarkResult) -> None:
        """Display a summary of benchmark results."""
        table = Table(title=f"Results: {result.benchmark_name}")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", justify="right")
        
        table.add_row("Max Concurrent Users", str(result.concurrent_users))
        table.add_row("Total Requests", str(result.total_requests))
        table.add_row("Successful", str(result.successful_requests))
        table.add_row("Failed", str(result.failed_requests))
        table.add_row("Avg Response Time", f"{result.avg_response_time_ms:.2f} ms")
        table.add_row("P95 Response Time", f"{result.p95_response_time_ms:.2f} ms")
        table.add_row("P99 Response Time", f"{result.p99_response_time_ms:.2f} ms")
        table.add_row("Requests/sec", f"{result.requests_per_second:.2f}")
        
        # Color-code error rate
        error_color = "green" if result.error_rate_percent < 1 else "yellow" if result.error_rate_percent < 5 else "red"
        table.add_row("Error Rate", f"[{error_color}]{result.error_rate_percent:.2f}%[/{error_color}]")
        
        if result.peak_cpu_percent > 0:
            table.add_row("Peak CPU", f"{result.peak_cpu_percent:.1f}%")
            table.add_row("Peak Memory", f"{result.peak_memory_mb:.1f} MB")
        
        console.print(table)
    
    def _write_results(self, results: List[BenchmarkResult]) -> None:
        """Write benchmark results to files."""
        if not results:
            return
        
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        
        # Write JSON for each result
        for result in results:
            json_path = self.results_writer.write_json(result)
            console.print(f"[dim]Results written to: {json_path}[/dim]")
        
        # Write combined CSV
        csv_path = self.results_writer.write_csv(
            results, 
            filename=f"benchmark_results_{timestamp}.csv"
        )
        console.print(f"[dim]CSV written to: {csv_path}[/dim]")
        
        # Write summary
        summary_path = self.results_writer.write_summary(
            results,
            filename=f"summary_{timestamp}.txt"
        )
        console.print(f"[dim]Summary written to: {summary_path}[/dim]")
    
    def display_final_summary(self) -> None:
        """Display a final summary of all benchmark results."""
        if not self._results:
            return
        
        console.print("\n")
        console.print(Panel(
            "[bold]BENCHMARK SUITE COMPLETE[/bold]",
            border_style="green",
        ))
        
        # Summary table
        table = Table(title="Final Results Summary")
        table.add_column("Benchmark", style="cyan")
        table.add_column("Max Users", justify="right")
        table.add_column("Requests", justify="right")
        table.add_column("Avg Time", justify="right")
        table.add_column("P95 Time", justify="right")
        table.add_column("RPS", justify="right")
        table.add_column("Errors", justify="right")
        
        for result in self._results:
            error_color = "green" if result.error_rate_percent < 1 else "yellow" if result.error_rate_percent < 5 else "red"
            table.add_row(
                result.benchmark_name,
                str(result.concurrent_users),
                str(result.total_requests),
                f"{result.avg_response_time_ms:.0f}ms",
                f"{result.p95_response_time_ms:.0f}ms",
                f"{result.requests_per_second:.1f}",
                f"[{error_color}]{result.error_rate_percent:.1f}%[/{error_color}]",
            )
        
        console.print(table)
        console.print()


async def run_benchmarks(
    benchmarks: List[Type[BaseBenchmark]],
    profile_id: str = "default",
    output_dir: Optional[Path] = None,
) -> List[BenchmarkResult]:
    """
    Convenience function to run multiple benchmarks.
    
    Args:
        benchmarks: List of benchmark classes to run
        profile_id: Compute profile to use
        output_dir: Output directory for results
        
    Returns:
        List of benchmark results
    """
    runner = BenchmarkRunner(profile_id=profile_id, output_dir=output_dir)
    
    for benchmark_class in benchmarks:
        runner.register_benchmark(benchmark_class)
    
    results = await runner.run_all()
    runner.display_final_summary()
    
    return results
