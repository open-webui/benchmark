"""
Command-line interface for Open WebUI Benchmark.

Provides commands for running benchmarks, managing compute profiles,
and analyzing results.
"""

import asyncio
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel

from benchmark.core.config import load_config, ConfigLoader
from benchmark.core.runner import BenchmarkRunner
from benchmark.scenarios.channels import ChannelConcurrencyBenchmark, ChannelWebSocketBenchmark


console = Console()


def print_banner():
    """Print the benchmark suite banner."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║          Open WebUI Benchmark Suite v0.1.0                ║
║          Testing performance at scale                      ║
╚═══════════════════════════════════════════════════════════╝
    """
    console.print(banner, style="bold blue")


def list_profiles():
    """List available compute profiles."""
    loader = ConfigLoader()
    profiles = loader.load_compute_profiles()
    
    console.print("\n[bold]Available Compute Profiles:[/bold]\n")
    
    for profile_id, profile in profiles.items():
        console.print(f"  [cyan]{profile_id}[/cyan]")
        console.print(f"    Name: {profile.name}")
        console.print(f"    Description: {profile.description}")
        console.print(f"    Resources: {profile.resources.cpus} CPUs, {profile.resources.memory} RAM")
        console.print()


def list_benchmarks():
    """List available benchmarks."""
    console.print("\n[bold]Available Benchmarks:[/bold]\n")
    
    benchmarks = [
        ("channels", ChannelConcurrencyBenchmark),
        ("channels-ws", ChannelWebSocketBenchmark),
    ]
    
    for cmd, benchmark_class in benchmarks:
        console.print(f"  [cyan]{cmd}[/cyan]")
        console.print(f"    Name: {benchmark_class.name}")
        console.print(f"    Description: {benchmark_class.description}")
        console.print()


async def run_channel_benchmark(
    profile_id: str = "default",
    target_url: Optional[str] = None,
    max_users: Optional[int] = None,
    step_size: Optional[int] = None,
    output_dir: Optional[str] = None,
):
    """Run the channel concurrency benchmark."""
    # Load config with overrides
    overrides = {}
    if target_url:
        overrides["target_url"] = target_url
    
    config = load_config(profile_id, overrides=overrides)
    
    if max_users:
        config.channels.max_concurrent_users = max_users
    
    if step_size:
        config.channels.user_step_size = step_size
    
    # Auto-adjust step size if larger than max users
    if config.channels.user_step_size > config.channels.max_concurrent_users:
        config.channels.user_step_size = config.channels.max_concurrent_users
    
    # Create runner
    runner = BenchmarkRunner(
        config=config,
        profile_id=profile_id,
        output_dir=Path(output_dir) if output_dir else None,
    )
    
    # Run benchmark
    result = await runner.run_benchmark(ChannelConcurrencyBenchmark)
    runner.display_final_summary()
    
    return result


async def run_channel_ws_benchmark(
    profile_id: str = "default",
    target_url: Optional[str] = None,
    max_users: Optional[int] = None,
    output_dir: Optional[str] = None,
):
    """Run the channel WebSocket benchmark."""
    # Load config with overrides
    overrides = {}
    if target_url:
        overrides["target_url"] = target_url
    
    config = load_config(profile_id, overrides=overrides)
    
    if max_users:
        config.channels.max_concurrent_users = max_users
    
    # Create runner
    runner = BenchmarkRunner(
        config=config,
        profile_id=profile_id,
        output_dir=Path(output_dir) if output_dir else None,
    )
    
    # Run benchmark
    result = await runner.run_benchmark(ChannelWebSocketBenchmark)
    runner.display_final_summary()
    
    return result


async def run_all_benchmarks(
    profile_id: str = "default",
    target_url: Optional[str] = None,
    output_dir: Optional[str] = None,
):
    """Run all available benchmarks."""
    # Load config with overrides
    overrides = {}
    if target_url:
        overrides["target_url"] = target_url
    
    config = load_config(profile_id, overrides=overrides)
    
    # Create runner and register all benchmarks
    runner = BenchmarkRunner(
        config=config,
        profile_id=profile_id,
        output_dir=Path(output_dir) if output_dir else None,
    )
    
    runner.register_benchmark(ChannelConcurrencyBenchmark)
    
    # Run all benchmarks
    results = await runner.run_all()
    runner.display_final_summary()
    
    return results


def main():
    """Main entry point for CLI."""
    import argparse
    
    print_banner()
    
    parser = argparse.ArgumentParser(
        description="Open WebUI Benchmark Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # List profiles command
    list_profiles_parser = subparsers.add_parser(
        "profiles",
        help="List available compute profiles",
    )
    
    # List benchmarks command
    list_benchmarks_parser = subparsers.add_parser(
        "list",
        help="List available benchmarks",
    )
    
    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run benchmarks",
    )
    run_parser.add_argument(
        "benchmark",
        nargs="?",
        default="all",
        choices=["all", "channels", "channels-ws"],
        help="Benchmark to run (default: all)",
    )
    run_parser.add_argument(
        "-p", "--profile",
        default="default",
        help="Compute profile to use (default: default)",
    )
    run_parser.add_argument(
        "-u", "--url",
        help="Target Open WebUI URL (default: from config)",
    )
    run_parser.add_argument(
        "-m", "--max-users",
        type=int,
        help="Maximum concurrent users to test",
    )
    run_parser.add_argument(
        "-s", "--step-size",
        type=int,
        help="User increment step size (default: 10)",
    )
    run_parser.add_argument(
        "-o", "--output",
        help="Output directory for results",
    )
    
    args = parser.parse_args()
    
    if args.command == "profiles":
        list_profiles()
    elif args.command == "list":
        list_benchmarks()
    elif args.command == "run":
        try:
            if args.benchmark == "all":
                asyncio.run(run_all_benchmarks(
                    profile_id=args.profile,
                    target_url=args.url,
                    output_dir=args.output,
                ))
            elif args.benchmark == "channels":
                asyncio.run(run_channel_benchmark(
                    profile_id=args.profile,
                    target_url=args.url,
                    max_users=args.max_users,
                    step_size=args.step_size,
                    output_dir=args.output,
                ))
            elif args.benchmark == "channels-ws":
                asyncio.run(run_channel_ws_benchmark(
                    profile_id=args.profile,
                    target_url=args.url,
                    max_users=args.max_users,
                    output_dir=args.output,
                ))
            else:
                console.print(f"[red]Unknown benchmark: {args.benchmark}[/red]")
                sys.exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Benchmark interrupted[/yellow]")
            sys.exit(1)
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            sys.exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
