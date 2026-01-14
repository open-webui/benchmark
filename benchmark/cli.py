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
from benchmark.auth import (
    ensure_admin_authenticated,
    AuthenticationError,
    ServiceNotReadyError,
)
from benchmark.auth.entrypoint import check_auth_status


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


async def auth_check(target_url: Optional[str] = None):
    """Check authentication configuration and service status."""
    console.print("\n[bold]Authentication Status Check[/bold]\n")
    
    with console.status("Checking configuration and service..."):
        status = await check_auth_status(base_url=target_url)
    
    # Display results
    console.print(f"  Service URL: [cyan]{status['service_url']}[/cyan]")
    
    if status['service_reachable']:
        console.print(f"  Service Status: [green]✓ Reachable[/green]")
    else:
        console.print(f"  Service Status: [red]✗ Not reachable[/red]")
    
    if status['credentials_configured']:
        console.print(f"  Credentials: [green]✓ Configured[/green]")
        console.print(f"  Admin Email: [cyan]{status['admin_email']}[/cyan]")
    else:
        console.print(f"  Credentials: [red]✗ Not configured[/red]")
        console.print("    Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD environment variables")
    
    console.print()
    
    # Summary
    if status['service_reachable'] and status['credentials_configured']:
        console.print("[green]Ready to run benchmarks![/green]")
        return True
    else:
        console.print("[yellow]Configuration incomplete. Fix issues above before running benchmarks.[/yellow]")
        return False


async def auth_verify(target_url: Optional[str] = None):
    """Verify authentication by actually signing in."""
    console.print("\n[bold]Authentication Verification[/bold]\n")
    
    try:
        with console.status("Authenticating..."):
            client, auth_result = await ensure_admin_authenticated(
                base_url=target_url,
                wait_for_service=True,
                service_wait_retries=10,
            )
        
        console.print(f"  [green]✓ Authentication successful![/green]")
        console.print(f"  User ID: [cyan]{auth_result.user.id}[/cyan]")
        console.print(f"  Email: [cyan]{auth_result.user.email}[/cyan]")
        console.print(f"  Role: [cyan]{auth_result.user.role}[/cyan]")
        
        if auth_result.is_new_signup:
            console.print(f"  [yellow]Note: Created new admin account (first run)[/yellow]")
        
        # Clean up
        await client.close()
        
        console.print("\n[green]Ready to run benchmarks![/green]")
        return True
        
    except ServiceNotReadyError as e:
        console.print(f"  [red]✗ Service not ready: {e}[/red]")
        return False
    except AuthenticationError as e:
        console.print(f"  [red]✗ Authentication failed: {e}[/red]")
        return False
    except Exception as e:
        console.print(f"  [red]✗ Unexpected error: {e}[/red]")
        return False


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
    
    # Auth command with subcommands
    auth_parser = subparsers.add_parser(
        "auth",
        help="Authentication commands",
    )
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", help="Auth subcommands")
    
    # Auth check subcommand
    auth_check_parser = auth_subparsers.add_parser(
        "check",
        help="Check auth configuration and service status (no actual auth)",
    )
    auth_check_parser.add_argument(
        "-u", "--url",
        help="Target Open WebUI URL (default: from config)",
    )
    
    # Auth verify subcommand
    auth_verify_parser = auth_subparsers.add_parser(
        "verify",
        help="Verify authentication by signing in",
    )
    auth_verify_parser.add_argument(
        "-u", "--url",
        help="Target Open WebUI URL (default: from config)",
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
    elif args.command == "auth":
        if args.auth_command == "check":
            success = asyncio.run(auth_check(target_url=args.url))
            sys.exit(0 if success else 1)
        elif args.auth_command == "verify":
            success = asyncio.run(auth_verify(target_url=args.url))
            sys.exit(0 if success else 1)
        else:
            auth_parser.print_help()
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
