"""
Channel concurrency benchmark.

Tests how many concurrent users can be in a Channel before the system
starts experiencing performance degradation.
"""

import asyncio
import random
import string
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.live import Live
from rich.table import Table

from benchmark.core.base import BaseBenchmark
from benchmark.core.config import BenchmarkConfig
from benchmark.core.metrics import MetricsCollector, BenchmarkResult
from benchmark.clients.http_client import OpenWebUIClient, ClientPool
from benchmark.clients.websocket_client import WebSocketClient, WebSocketPool


console = Console()


def generate_message_content(min_length: int = 50, max_length: int = 500) -> str:
    """Generate random message content."""
    length = random.randint(min_length, max_length)
    words = []
    current_length = 0
    
    while current_length < length:
        word_length = random.randint(3, 10)
        word = ''.join(random.choices(string.ascii_lowercase, k=word_length))
        words.append(word)
        current_length += word_length + 1
    
    return ' '.join(words)[:length]


class ChannelConcurrencyBenchmark(BaseBenchmark):
    """
    Benchmark for testing channel concurrent user capacity.
    
    This benchmark:
    1. Creates a test channel
    2. Progressively adds users up to a maximum
    3. Has each user send messages at a configured rate
    4. Measures response times and error rates at each level
    5. Identifies the point where performance degrades
    """
    
    name = "Channel Concurrency"
    description = "Test concurrent user capacity in Open WebUI Channels"
    version = "1.0.0"
    
    def __init__(self, config: BenchmarkConfig):
        """Initialize the channel concurrency benchmark."""
        super().__init__(config)
        
        self._admin_client: Optional[OpenWebUIClient] = None
        self._client_pool: Optional[ClientPool] = None
        self._ws_pool: Optional[WebSocketPool] = None
        self._test_channel_id: Optional[str] = None
        self._created_users: List[str] = []  # Track user IDs for cleanup
        
    async def setup(self) -> None:
        """
        Set up the benchmark environment.
        
        Uses admin credentials to:
        1. Create a test channel
        2. Create temporary benchmark users dynamically
        
        Requires ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD in environment.
        """
        # Validate that we have admin credentials configured
        if not self.config.admin_user:
            raise RuntimeError(
                "Admin user credentials not configured. "
                "Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD environment variables."
            )
        
        # Create admin client
        self._admin_client = OpenWebUIClient(
            self.config.target_url,
            self.config.request_timeout,
        )
        await self._admin_client.connect()
        
        # Wait for service to be ready
        if not await self._admin_client.wait_for_ready():
            raise RuntimeError("Open WebUI service not ready")
        
        # Authenticate admin
        admin_config = self.config.admin_user
        try:
            await self._admin_client.signin(admin_config.email, admin_config.password)
        except Exception:
            try:
                await self._admin_client.signup(
                    admin_config.email,
                    admin_config.password,
                    admin_config.name,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to authenticate admin ({admin_config.email}): {e}"
                )
        
        # Create test channel
        channel_name = f"benchmark-channel-{int(time.time())}"
        channel = await self._admin_client.create_channel(
            name=channel_name,
            description="Benchmark test channel - will be deleted after test",
            access_control=None,  # Public channel for benchmark
        )
        self._test_channel_id = channel["id"]
        
        # Initialize client pool
        self._client_pool = ClientPool(
            self.config.target_url,
            self.config.request_timeout,
        )
        
    async def run(self) -> BenchmarkResult:
        """
        Execute the channel concurrency benchmark.
        
        Progressively increases concurrent users and measures performance
        at each level.
        
        Returns:
            BenchmarkResult with metrics from the benchmark
        """
        channel_config = self.config.channels
        max_users = channel_config.max_concurrent_users
        step_size = channel_config.user_step_size
        sustain_time = channel_config.sustain_time
        message_frequency = channel_config.message_frequency
        
        all_results: List[BenchmarkResult] = []
        
        # Calculate total levels for progress
        total_levels = (max_users + step_size - 1) // step_size
        current_level = 0
        
        # Progressive load testing
        current_users = step_size
        
        console.print(f"\n[bold cyan]Testing {step_size} to {max_users} concurrent users (step: {step_size})[/bold cyan]")
        console.print(f"[dim]Each level runs for {sustain_time}s with {self.config.cooldown_seconds}s cooldown[/dim]\n")
        
        while current_users <= max_users:
            current_level += 1
            console.print(f"[yellow]━━━ Level {current_level}/{total_levels}: {current_users} users ━━━[/yellow]")
            
            # Run benchmark at this level
            result = await self._run_at_user_level(
                user_count=current_users,
                duration=sustain_time,
                message_frequency=message_frequency,
            )
            
            all_results.append(result)
            
            # Show level results
            status_color = "green" if result.error_rate_percent < 5 else "yellow" if result.error_rate_percent < 10 else "red"
            console.print(f"  Requests: {result.total_requests} | "
                         f"Avg: {result.avg_response_time_ms:.1f}ms | "
                         f"P95: {result.p95_response_time_ms:.1f}ms | "
                         f"[{status_color}]Errors: {result.error_rate_percent:.1f}%[/{status_color}]")
            
            # Check if we should stop (too many errors)
            if result.error_rate_percent > self.config.thresholds.max_error_rate_percent * 2:
                console.print(f"[red]⚠ Stopping early - error rate too high ({result.error_rate_percent:.1f}%)[/red]")
                break
            
            # Increase user count
            current_users += step_size
            
            # Brief cooldown between levels (except last)
            if current_users <= max_users:
                console.print(f"[dim]  Cooldown {self.config.cooldown_seconds}s...[/dim]")
                await asyncio.sleep(self.config.cooldown_seconds)
        
        console.print()
        
        # Find the best sustainable user count
        return self._analyze_results(all_results)
    
    async def _run_at_user_level(
        self,
        user_count: int,
        duration: float,
        message_frequency: float,
    ) -> BenchmarkResult:
        """
        Run benchmark at a specific user count level.
        
        Args:
            user_count: Number of concurrent users
            duration: How long to sustain the load
            message_frequency: Messages per second per user
            
        Returns:
            BenchmarkResult for this level
        """
        metrics = MetricsCollector()
        
        # Create benchmark users via admin API with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Creating {user_count} users...", total=user_count * 2)
            
            def update_progress(current: int, total: int):
                progress.update(task, completed=current)
            
            clients = await self._client_pool.create_benchmark_users(
                admin_client=self._admin_client,
                count=user_count,
                email_pattern="benchmark_user_{n}@test.local",
                password="benchmark_pass_123",
                name_pattern="Benchmark User {n}",
                progress_callback=update_progress,
            )
        
        console.print(f"  [green]✓[/green] Created {len(clients)} users")
        
        # Calculate message interval
        if message_frequency > 0:
            message_interval = 1.0 / message_frequency
        else:
            message_interval = float('inf')
        
        # Run the actual benchmark
        console.print(f"  [cyan]▶[/cyan] Running load test for {duration}s...")
        metrics.start()
        
        # Create tasks for each user
        end_time = time.time() + duration
        tasks = []
        
        for client in clients:
            task = asyncio.create_task(
                self._user_activity(
                    client=client,
                    channel_id=self._test_channel_id,
                    message_interval=message_interval,
                    end_time=end_time,
                    metrics=metrics,
                )
            )
            tasks.append(task)
        
        # Wait for all tasks to complete
        await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics.stop()
        
        # Clean up: close clients and delete benchmark users
        await self._client_pool.close_all()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task(f"Cleaning up {user_count} users...", total=user_count)
            
            def cleanup_progress(current: int, total: int):
                progress.update(task, completed=current)
            
            await self._client_pool.cleanup_benchmark_users(
                self._admin_client,
                progress_callback=cleanup_progress,
            )
        
        console.print(f"  [green]✓[/green] Cleanup complete")
        
        # Get result
        result = metrics.get_result(
            benchmark_name=f"Channel @ {user_count} users",
            concurrent_users=user_count,
            metadata={"user_count": user_count, "duration": duration},
        )
        
        return result
    
    async def _user_activity(
        self,
        client: OpenWebUIClient,
        channel_id: str,
        message_interval: float,
        end_time: float,
        metrics: MetricsCollector,
    ) -> None:
        """
        Simulate user activity in a channel.
        
        Args:
            client: HTTP client for the user
            channel_id: Channel to send messages to
            message_interval: Time between messages
            end_time: When to stop
            metrics: Metrics collector
        """
        message_size = self.config.channels.message_size
        
        while time.time() < end_time:
            try:
                # Generate message
                content = generate_message_content(
                    min_length=message_size.get("min", 50),
                    max_length=message_size.get("max", 500),
                )
                
                # Send message and time it
                start = time.time()
                try:
                    await client.post_message(channel_id, content)
                    duration_ms = (time.time() - start) * 1000
                    metrics.record_timing(
                        operation="post_message",
                        duration_ms=duration_ms,
                        success=True,
                        metadata={"user": client.user.email if client.user else "unknown"},
                    )
                except Exception as e:
                    duration_ms = (time.time() - start) * 1000
                    metrics.record_timing(
                        operation="post_message",
                        duration_ms=duration_ms,
                        success=False,
                        error=str(e),
                    )
                
                # Also fetch messages periodically
                if random.random() < 0.3:  # 30% chance
                    start = time.time()
                    try:
                        await client.get_channel_messages(channel_id, limit=20)
                        duration_ms = (time.time() - start) * 1000
                        metrics.record_timing(
                            operation="get_messages",
                            duration_ms=duration_ms,
                            success=True,
                        )
                    except Exception as e:
                        duration_ms = (time.time() - start) * 1000
                        metrics.record_timing(
                            operation="get_messages",
                            duration_ms=duration_ms,
                            success=False,
                            error=str(e),
                        )
                
                # Wait before next message
                # Add some jitter to avoid thundering herd
                jitter = random.uniform(0.8, 1.2)
                await asyncio.sleep(message_interval * jitter)
                
            except asyncio.CancelledError:
                break
            except Exception:
                # Continue on other errors
                await asyncio.sleep(0.5)
    
    def _analyze_results(self, results: List[BenchmarkResult]) -> BenchmarkResult:
        """
        Analyze results from all user levels.
        
        Finds the maximum sustainable user count and returns a summary result.
        
        Args:
            results: Results from each user level
            
        Returns:
            Summary BenchmarkResult
        """
        if not results:
            return BenchmarkResult(
                benchmark_name=self.name,
                timestamp=datetime.utcnow(),
                passed=False,
            )
        
        # Find the highest user count that passed thresholds
        max_sustainable_users = 0
        best_result = results[0]
        
        for result in results:
            # Check if this level meets thresholds
            passes_response_time = (
                result.p95_response_time_ms <= self.config.thresholds.max_p95_response_time_ms
            )
            passes_error_rate = (
                result.error_rate_percent <= self.config.thresholds.max_error_rate_percent
            )
            
            if passes_response_time and passes_error_rate:
                if result.concurrent_users > max_sustainable_users:
                    max_sustainable_users = result.concurrent_users
                    best_result = result
        
        # Create summary result
        summary = BenchmarkResult(
            benchmark_name=self.name,
            timestamp=datetime.utcnow(),
            concurrent_users=max_sustainable_users,
            total_requests=sum(r.total_requests for r in results),
            successful_requests=sum(r.successful_requests for r in results),
            failed_requests=sum(r.failed_requests for r in results),
            avg_response_time_ms=best_result.avg_response_time_ms,
            min_response_time_ms=min(r.min_response_time_ms for r in results if r.min_response_time_ms > 0),
            max_response_time_ms=max(r.max_response_time_ms for r in results),
            p50_response_time_ms=best_result.p50_response_time_ms,
            p95_response_time_ms=best_result.p95_response_time_ms,
            p99_response_time_ms=best_result.p99_response_time_ms,
            requests_per_second=best_result.requests_per_second,
            total_duration_seconds=sum(r.total_duration_seconds for r in results),
            error_rate_percent=best_result.error_rate_percent,
            iterations=len(results),
            metadata={
                "max_sustainable_users": max_sustainable_users,
                "tested_levels": [r.concurrent_users for r in results],
                "results_by_level": [
                    {
                        "users": r.concurrent_users,
                        "p95_ms": r.p95_response_time_ms,
                        "error_rate": r.error_rate_percent,
                    }
                    for r in results
                ],
            },
        )
        
        # Determine if passed
        summary.passed = max_sustainable_users > 0
        
        return summary
    
    async def teardown(self) -> None:
        """Clean up benchmark resources."""
        # Delete test channel
        if self._test_channel_id and self._admin_client:
            try:
                await self._admin_client.delete_channel(self._test_channel_id)
            except Exception:
                pass
        
        # Close admin client
        if self._admin_client:
            await self._admin_client.close()
        
        # Close any remaining pooled clients
        if self._client_pool:
            await self._client_pool.close_all()
        
        # Close WebSocket connections
        if self._ws_pool:
            await self._ws_pool.close_all()


class ChannelWebSocketBenchmark(BaseBenchmark):
    """
    Benchmark for testing channel WebSocket scalability.
    
    Tests real-time message delivery through WebSockets rather than
    HTTP polling.
    """
    
    name = "Channel WebSocket"
    description = "Test WebSocket scalability in Open WebUI Channels"
    version = "1.0.0"
    
    def __init__(self, config: BenchmarkConfig):
        """Initialize the WebSocket benchmark."""
        super().__init__(config)
        
        self._admin_client: Optional[OpenWebUIClient] = None
        self._client_pool: Optional[ClientPool] = None
        self._ws_pool: Optional[WebSocketPool] = None
        self._test_channel_id: Optional[str] = None
    
    async def setup(self) -> None:
        """Set up benchmark environment."""
        # Similar to ChannelConcurrencyBenchmark setup
        self._admin_client = OpenWebUIClient(
            self.config.target_url,
            self.config.request_timeout,
        )
        await self._admin_client.connect()
        
        if not await self._admin_client.wait_for_ready():
            raise RuntimeError("Open WebUI service not ready")
        
        # Authenticate admin
        admin_config = self.config.admin_user
        if not admin_config:
            raise RuntimeError(
                "Admin credentials not configured. "
                "Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD."
            )
        
        try:
            await self._admin_client.signin(admin_config.email, admin_config.password)
        except Exception:
            try:
                await self._admin_client.signup(
                    admin_config.email,
                    admin_config.password,
                    admin_config.name,
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to authenticate admin ({admin_config.email}): {e}"
                )
        
        # Create test channel
        channel_name = f"benchmark-ws-channel-{int(time.time())}"
        channel = await self._admin_client.create_channel(
            name=channel_name,
            description="WebSocket benchmark channel",
        )
        self._test_channel_id = channel["id"]
        
        # Initialize pools
        self._client_pool = ClientPool(self.config.target_url, self.config.request_timeout)
        self._ws_pool = WebSocketPool(self.config.target_url, self.config.websocket_timeout)
    
    async def run(self) -> BenchmarkResult:
        """
        Execute WebSocket benchmark.
        
        Tests message delivery latency through WebSockets.
        """
        metrics = MetricsCollector()
        metrics.start()
        
        channel_config = self.config.channels
        user_count = min(channel_config.max_concurrent_users, 50)  # Limit for WS test
        
        # Create test users
        clients = await self._client_pool.create_benchmark_users(
            admin_client=self._admin_client,
            count=user_count,
            email_pattern=self.config.user_template.email_pattern,
            password=self.config.user_template.password,
            name_pattern=self.config.user_template.name_pattern,
        )
        
        # Create WebSocket connections
        tokens = [client.token for client in clients if client.token]
        ws_clients = await self._ws_pool.create_connections(tokens)
        
        # Run test - measure message propagation time
        duration = channel_config.sustain_time
        end_time = time.time() + duration
        
        message_count = 0
        while time.time() < end_time:
            # Pick random sender
            sender = random.choice(clients)
            
            # Track start time
            start = time.time()
            
            try:
                # Send message via HTTP
                content = f"Test message {message_count}"
                await sender.post_message(self._test_channel_id, content)
                
                duration_ms = (time.time() - start) * 1000
                metrics.record_timing(
                    operation="send_message",
                    duration_ms=duration_ms,
                    success=True,
                )
                message_count += 1
                
            except Exception as e:
                metrics.record_timing(
                    operation="send_message",
                    duration_ms=(time.time() - start) * 1000,
                    success=False,
                    error=str(e),
                )
            
            await asyncio.sleep(0.5)  # Message rate
        
        metrics.stop()
        
        return metrics.get_result(
            benchmark_name=self.name,
            concurrent_users=user_count,
            metadata={
                "websocket_connections": len(ws_clients),
                "messages_sent": message_count,
            },
        )
    
    async def teardown(self) -> None:
        """Clean up resources."""
        if self._test_channel_id and self._admin_client:
            try:
                await self._admin_client.delete_channel(self._test_channel_id)
            except Exception:
                pass
        
        if self._admin_client:
            await self._admin_client.close()
        
        if self._client_pool:
            await self._client_pool.close_all()
        
        if self._ws_pool:
            await self._ws_pool.close_all()
