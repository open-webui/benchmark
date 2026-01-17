"""
AI Chat API concurrency benchmark.

Tests how Open WebUI performs when multiple users are simultaneously
interacting with AI models via streaming chat completions through the API.
"""

import asyncio
import random
import time
from typing import Optional, List

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from benchmark.core.base import BaseBenchmark
from benchmark.core.config import BenchmarkConfig
from benchmark.core.metrics import MetricsCollector, BenchmarkResult
from benchmark.clients.http_client import OpenWebUIClient, ClientPool
from benchmark.auth import ensure_admin_authenticated, AuthenticationError, ServiceNotReadyError


console = Console()


class ChatAPIBenchmark(BaseBenchmark):
    """
    Benchmark for testing concurrent AI chat performance via API.
    
    This benchmark:
    1. Verifies the configured model is available
    2. Creates test users for concurrent chat sessions
    3. Sends concurrent streaming chat requests via the API
    4. Measures TTFT, tokens/second, and total response time
    5. Uses cache-optimized prompts to reduce OpenAI costs
    """
    
    name = "Chat API Concurrency"
    description = "Test concurrent AI chat performance via OpenAI API"
    version = "1.0.0"
    
    def __init__(
        self,
        config: BenchmarkConfig,
        admin_client: Optional[OpenWebUIClient] = None,
    ):
        """
        Initialize the chat concurrency benchmark.
        
        Args:
            config: Benchmark configuration
            admin_client: Optional pre-authenticated admin client
        """
        super().__init__(config)
        
        self._admin_client: Optional[OpenWebUIClient] = admin_client
        self._owns_admin_client: bool = admin_client is None
        self._client_pool: Optional[ClientPool] = None
        self._test_clients: List[OpenWebUIClient] = []
    
    async def setup(self) -> None:
        """
        Set up the benchmark environment.
        
        Authenticates admin, verifies model availability, configures model
        for public access, and creates test users.
        """
        # Authenticate admin if needed
        if self._admin_client is None:
            try:
                self._admin_client, _auth_result = await ensure_admin_authenticated(
                    base_url=self.config.target_url,
                    timeout=self.config.request_timeout,
                    wait_for_service=True,
                )
            except ServiceNotReadyError as e:
                raise RuntimeError(f"Open WebUI service not ready: {e}")
            except AuthenticationError as e:
                raise RuntimeError(f"Admin authentication failed: {e}")
        
        # Verify the configured model is available
        chat_config = self.config.chat
        model_available = await self._admin_client.verify_model_available(chat_config.model)
        
        if not model_available:
            available_models = await self._admin_client.get_models()
            model_names = [m.get("id", m.get("name", str(m))) for m in available_models[:10]]
            raise RuntimeError(
                f"Model '{chat_config.model}' is not available. "
                f"Available models: {', '.join(model_names)}"
                f"\nEnsure OpenAI API key is configured in Open WebUI settings, "
                f"or set CHAT_BENCHMARK_MODEL to an available model."
            )
        
        # Configure model for public access so benchmark users can use it
        made_public = await self._admin_client.make_model_public(chat_config.model)
        if not made_public:
            raise RuntimeError(
                f"Failed to configure model '{chat_config.model}' for public access. "
                f"Ensure you have admin privileges."
            )
        
        # Initialize client pool and create test users
        self._client_pool = ClientPool(
            self.config.target_url,
            self.config.request_timeout,
        )
        
        user_count = chat_config.max_concurrent_users
        
        # Create benchmark users with progress display
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
            
            self._test_clients = await self._client_pool.create_benchmark_users(
                admin_client=self._admin_client,
                count=user_count,
                email_pattern="chat_benchmark_{n}@test.local",
                password="chat_benchmark_pass_123",
                name_pattern="Chat Benchmark User {n}",
                progress_callback=update_progress,
            )
        
        console.print(f"[green]✓[/green] Created {len(self._test_clients)} users")
    
    async def run(self) -> BenchmarkResult:
        """
        Execute the chat concurrency benchmark.
        
        Runs concurrent chat requests and measures performance metrics.
        
        Returns:
            BenchmarkResult with timing and token metrics
        """
        chat_config = self.config.chat
        metrics = MetricsCollector()
        metrics.start()
        
        user_count = len(self._test_clients)
        requests_per_user = chat_config.requests_per_user
        total_requests = user_count * requests_per_user
        
        console.print(f"\n[bold cyan]Running chat benchmark[/bold cyan]")
        console.print(f"[dim]Model: {chat_config.model}[/dim]")
        console.print(f"[dim]Concurrent users: {user_count}[/dim]")
        console.print(f"[dim]Requests per user: {requests_per_user}[/dim]")
        console.print(f"[dim]Total requests: {total_requests}[/dim]\n")
        
        # Build messages with fixed system prompt for cache optimization
        system_message = {"role": "system", "content": chat_config.system_prompt}
        
        # Track completed requests
        completed = 0
        errors = 0
        
        # Progress bar for tracking requests
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        )
        progress.start()
        task = progress.add_task("Running requests...", total=total_requests)
        
        def update_status():
            progress.update(task, completed=completed + errors, 
                          description=f"Completed: {completed} | Errors: {errors}")
        
        async def run_user_session(client: OpenWebUIClient, user_num: int):
            """Run chat requests for a single user."""
            nonlocal completed, errors
            
            for req_num in range(requests_per_user):
                # Select a random prompt from the pool
                user_prompt = random.choice(chat_config.prompt_pool)
                messages = [
                    system_message,
                    {"role": "user", "content": user_prompt},
                ]
                
                try:
                    result = await client.stream_chat_completion(
                        messages=messages,
                        model=chat_config.model,
                        temperature=0.7,
                        max_tokens=100,  # Keep responses short
                    )
                    
                    metrics.record_streaming_timing(
                        operation="chat_completion",
                        duration_ms=result.total_duration_ms,
                        ttft_ms=result.ttft_ms,
                        tokens_generated=result.tokens_generated,
                        success=True,
                        metadata={
                            "user": user_num,
                            "request": req_num,
                            "model": chat_config.model,
                            "prompt": user_prompt[:50],
                        },
                    )
                    completed += 1
                    update_status()
                    
                except Exception as e:
                    metrics.record_streaming_timing(
                        operation="chat_completion",
                        duration_ms=0,
                        ttft_ms=0,
                        tokens_generated=0,
                        success=False,
                        error=str(e),
                        metadata={
                            "user": user_num,
                            "request": req_num,
                            "model": chat_config.model,
                        },
                    )
                    errors += 1
                    update_status()
                
                # Small delay between requests from same user
                await asyncio.sleep(0.1)
        
        # Run all user sessions concurrently
        tasks = [
            run_user_session(client, i) 
            for i, client in enumerate(self._test_clients)
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
        
        metrics.stop()
        
        # Finish progress bar
        progress.update(task, description="Complete!", completed=total_requests)
        progress.stop()
        
        return metrics.get_result(
            benchmark_name=self.name,
            concurrent_users=user_count,
            metadata={
                "model": chat_config.model,
                "requests_per_user": requests_per_user,
                "total_requests": total_requests,
                "prompt_pool_size": len(chat_config.prompt_pool),
            },
        )
    
    async def teardown(self) -> None:
        """Clean up benchmark resources."""
        # Close test user clients and clean up users
        if self._client_pool:
            await self._client_pool.close_all()
        
        # Close admin client if we created it
        if self._admin_client and self._owns_admin_client:
            await self._admin_client.close()
