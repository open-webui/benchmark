"""
HTTP client for interacting with Open WebUI API.

Provides async HTTP methods for authentication, channel management, and messaging.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List, Callable, AsyncIterator
from dataclasses import dataclass, field
import httpx


@dataclass
class User:
    """Represents an authenticated user."""
    id: str
    email: str
    name: str
    role: str
    token: str


@dataclass
class StreamingChatResult:
    """Result from a streaming chat completion."""
    content: str
    tokens_generated: int
    ttft_ms: float  # Time to first token in milliseconds
    total_duration_ms: float
    model: str
    finish_reason: Optional[str] = None
    
    @property
    def tokens_per_second(self) -> float:
        """Calculate tokens per second."""
        if self.total_duration_ms > 0:
            return self.tokens_generated / (self.total_duration_ms / 1000)
        return 0.0


class OpenWebUIClient:
    """
    Async HTTP client for Open WebUI API.
    
    Handles authentication and provides methods for common API operations.
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the Open WebUI instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._user: Optional[User] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def connect(self) -> None:
        """Initialize the HTTP client."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            follow_redirects=True,
        )
    
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    @property
    def client(self) -> httpx.AsyncClient:
        """Get the HTTP client, ensuring it's initialized."""
        if self._client is None:
            raise RuntimeError("Client not connected. Call connect() first or use async context manager.")
        return self._client
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get headers including authorization if authenticated."""
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers
    
    @property
    def user(self) -> Optional[User]:
        """Get the current authenticated user."""
        return self._user
    
    @property
    def token(self) -> Optional[str]:
        """Get the current authentication token."""
        return self._token
    
    # ==================== Authentication ====================
    
    async def signup(
        self,
        email: str,
        password: str,
        name: str,
    ) -> User:
        """
        Create a new user account.
        
        Args:
            email: User email
            password: User password
            name: User display name
            
        Returns:
            User object with authentication token
        """
        response = await self.client.post(
            "/api/v1/auths/signup",
            json={
                "email": email,
                "password": password,
                "name": name,
            },
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        
        data = response.json()
        self._token = data.get("token")
        self._user = User(
            id=data.get("id"),
            email=email,
            name=name,
            role=data.get("role", "user"),
            token=self._token,
        )
        
        return self._user
    
    async def signin(self, email: str, password: str) -> User:
        """
        Authenticate an existing user.
        
        Args:
            email: User email
            password: User password
            
        Returns:
            User object with authentication token
        """
        response = await self.client.post(
            "/api/v1/auths/signin",
            json={
                "email": email,
                "password": password,
            },
            headers={"Content-Type": "application/json"},
        )
        response.raise_for_status()
        
        data = response.json()
        self._token = data.get("token")
        self._user = User(
            id=data.get("id"),
            email=email,
            name=data.get("name", ""),
            role=data.get("role", "user"),
            token=self._token,
        )
        
        return self._user
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Get the current authenticated user's information."""
        response = await self.client.get(
            "/api/v1/auths/",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    # ==================== Admin User Management ====================
    
    async def admin_create_user(
        self,
        email: str,
        password: str,
        name: str,
        role: str = "user",
    ) -> Dict[str, Any]:
        """
        Create a new user as admin.
        
        Requires the client to be authenticated as an admin user.
        
        Args:
            email: User email
            password: User password
            name: User display name
            role: User role (default: "user")
            
        Returns:
            Created user data including token
        """
        response = await self.client.post(
            "/api/v1/auths/add",
            json={
                "email": email,
                "password": password,
                "name": name,
                "role": role,
            },
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    async def admin_delete_user(self, user_id: str) -> bool:
        """
        Delete a user as admin.
        
        Requires the client to be authenticated as an admin user.
        
        Args:
            user_id: ID of the user to delete
            
        Returns:
            True if successful
        """
        response = await self.client.delete(
            f"/api/v1/users/{user_id}",
            headers=self.headers,
        )
        response.raise_for_status()
        return True
        return response.json()
    
    # ==================== Channels ====================
    
    async def get_channels(self) -> List[Dict[str, Any]]:
        """
        Get list of channels accessible to the current user.
        
        Returns:
            List of channel dictionaries
        """
        response = await self.client.get(
            "/api/v1/channels/",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    async def create_channel(
        self,
        name: str,
        description: Optional[str] = None,
        access_control: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Create a new channel (admin only).
        
        Args:
            name: Channel name
            description: Optional channel description
            access_control: Optional access control settings
            
        Returns:
            Created channel dictionary
        """
        payload = {
            "name": name,
        }
        if description:
            payload["description"] = description
        if access_control:
            payload["access_control"] = access_control
        
        response = await self.client.post(
            "/api/v1/channels/create",
            json=payload,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    async def get_channel(self, channel_id: str) -> Dict[str, Any]:
        """
        Get a specific channel by ID.
        
        Args:
            channel_id: Channel ID
            
        Returns:
            Channel dictionary
        """
        response = await self.client.get(
            f"/api/v1/channels/{channel_id}",
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    async def delete_channel(self, channel_id: str) -> bool:
        """
        Delete a channel (admin only).
        
        Args:
            channel_id: Channel ID
            
        Returns:
            True if successful
        """
        response = await self.client.delete(
            f"/api/v1/channels/{channel_id}/delete",
            headers=self.headers,
        )
        response.raise_for_status()
        return True
    
    # ==================== Messages ====================
    
    async def get_channel_messages(
        self,
        channel_id: str,
        skip: int = 0,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get messages from a channel.
        
        Args:
            channel_id: Channel ID
            skip: Number of messages to skip
            limit: Maximum number of messages to return
            
        Returns:
            List of message dictionaries
        """
        response = await self.client.get(
            f"/api/v1/channels/{channel_id}/messages",
            params={"skip": skip, "limit": limit},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    async def post_message(
        self,
        channel_id: str,
        content: str,
        parent_id: Optional[str] = None,
        data: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Post a message to a channel.
        
        Args:
            channel_id: Channel ID
            content: Message content
            parent_id: Optional parent message ID for threads
            data: Optional additional message data
            
        Returns:
            Created message dictionary
        """
        payload = {
            "content": content,
        }
        if parent_id:
            payload["parent_id"] = parent_id
        if data:
            payload["data"] = data
        
        response = await self.client.post(
            f"/api/v1/channels/{channel_id}/messages/post",
            json=payload,
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()
    
    # ==================== Health Check ====================
    
    async def health_check(self) -> bool:
        """
        Check if the Open WebUI instance is healthy.
        
        Returns:
            True if healthy
        """
        try:
            response = await self.client.get("/health")
            return response.status_code == 200
        except Exception:
            return False
    
    async def wait_for_ready(self, timeout: float = 60.0, interval: float = 2.0) -> bool:
        """
        Wait for the Open WebUI instance to become ready.
        
        Args:
            timeout: Maximum time to wait in seconds
            interval: Time between checks in seconds
            
        Returns:
            True if ready, False if timeout
        """
        elapsed = 0.0
        while elapsed < timeout:
            if await self.health_check():
                return True
            await asyncio.sleep(interval)
            elapsed += interval
        return False
    
    # ==================== Chat Completions ====================
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """
        Get list of available models.
        
        Returns:
            List of model dictionaries
        """
        response = await self.client.get(
            "/api/models",
            headers=self.headers,
        )
        response.raise_for_status()
        data = response.json()
        # Handle both direct list and wrapped response formats
        if isinstance(data, list):
            return data
        return data.get("data", data.get("models", []))
    
    async def verify_model_available(self, model_id: str) -> bool:
        """
        Check if a specific model is available.
        
        Args:
            model_id: The model identifier to check
            
        Returns:
            True if model is available, False otherwise
        """
        try:
            models = await self.get_models()
            model_ids = []
            for m in models:
                # Handle different model response formats
                if isinstance(m, dict):
                    model_ids.append(m.get("id", ""))
                    model_ids.append(m.get("name", ""))
                elif isinstance(m, str):
                    model_ids.append(m)
            return model_id in model_ids
        except Exception:
            return False
    
    async def make_model_public(self, model_id: str) -> bool:
        """
        Configure a model to be publicly accessible to all users.
        
        This creates a model configuration with access_control=None,
        which makes the model visible to all users, not just admins.
        
        Requires admin authentication.
        
        Args:
            model_id: The model identifier to make public
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # First check if model config already exists
            response = await self.client.get(
                f"/api/v1/models/model?id={model_id}",
                headers=self.headers,
            )
            
            if response.status_code == 200:
                # Model config exists, update it
                existing = response.json()
                update_payload = {
                    "id": model_id,
                    "base_model_id": existing.get("base_model_id", model_id),
                    "name": existing.get("name", model_id),
                    "params": existing.get("params", {}),
                    "meta": existing.get("meta", {}),
                    "access_control": None,  # None = public access
                }
                response = await self.client.post(
                    "/api/v1/models/model/update",
                    json=update_payload,
                    headers=self.headers,
                )
            else:
                # Create new model config with public access
                model_config = {
                    "id": model_id,
                    "base_model_id": model_id,
                    "name": model_id,
                    "params": {},
                    "meta": {
                        "description": f"Benchmark model: {model_id}",
                    },
                    "access_control": None,  # None = public access
                }
                response = await self.client.post(
                    "/api/v1/models/create",
                    json=model_config,
                    headers=self.headers,
                )
            
            response.raise_for_status()
            return True
        except Exception:
            return False
    
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> StreamingChatResult:
        """
        Send a streaming chat completion request and collect the response.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model ID to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            
        Returns:
            StreamingChatResult with content, timing, and token metrics
        """
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        start_time = time.time()
        first_token_time: Optional[float] = None
        content_chunks: List[str] = []
        tokens_generated = 0
        finish_reason = None
        
        async with self.client.stream(
            "POST",
            "/api/chat/completions",
            json=payload,
            headers=self.headers,
            timeout=120.0,  # Longer timeout for completions
        ) as response:
            response.raise_for_status()
            
            async for line in response.aiter_lines():
                if not line:
                    continue
                    
                # Handle SSE format: "data: {...}"
                if line.startswith("data: "):
                    data_str = line[6:]  # Remove "data: " prefix
                    
                    if data_str.strip() == "[DONE]":
                        break
                    
                    try:
                        data = json.loads(data_str)
                        
                        # Extract content from delta
                        choices = data.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content", "")
                            
                            if content:
                                # Record time to first token
                                if first_token_time is None:
                                    first_token_time = time.time()
                                
                                content_chunks.append(content)
                                tokens_generated += 1  # Approximate: 1 chunk ≈ 1 token
                            
                            # Check for finish reason
                            if choices[0].get("finish_reason"):
                                finish_reason = choices[0]["finish_reason"]
                    except json.JSONDecodeError:
                        continue
        
        end_time = time.time()
        total_duration_ms = (end_time - start_time) * 1000
        ttft_ms = (first_token_time - start_time) * 1000 if first_token_time else total_duration_ms
        
        return StreamingChatResult(
            content="".join(content_chunks),
            tokens_generated=tokens_generated,
            ttft_ms=ttft_ms,
            total_duration_ms=total_duration_ms,
            model=model,
            finish_reason=finish_reason,
        )
    
    async def create_chat(
        self,
        title: str = "Benchmark Chat",
    ) -> Dict[str, Any]:
        """
        Create a new chat session.
        
        Args:
            title: Chat title
            
        Returns:
            Created chat data including ID
        """
        response = await self.client.post(
            "/api/v1/chats/new",
            json={"title": title},
            headers=self.headers,
        )
        response.raise_for_status()
        return response.json()


class ClientPool:
    """
    Pool of HTTP clients for concurrent benchmark operations.
    
    Manages multiple authenticated clients for simulating concurrent users.
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ):
        """
        Initialize the client pool.
        
        Args:
            base_url: Base URL of the Open WebUI instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self._clients: List[OpenWebUIClient] = []
    
    async def create_clients(
        self,
        count: int,
        email_pattern: str = "user{n}@benchmark.local",
        password: str = "benchmark_password_123",
        name_pattern: str = "Test User {n}",
    ) -> List[OpenWebUIClient]:
        """
        Create and authenticate multiple clients.
        
        Args:
            count: Number of clients to create
            email_pattern: Email pattern with {n} placeholder
            password: Password for all users
            name_pattern: Name pattern with {n} placeholder
            
        Returns:
            List of authenticated clients
        """
        clients = []
        
        for i in range(count):
            client = OpenWebUIClient(self.base_url, self.timeout)
            await client.connect()
            
            email = email_pattern.format(n=i + 1)
            name = name_pattern.format(n=i + 1)
            
            try:
                # Try to sign in first (user might already exist)
                await client.signin(email, password)
            except httpx.HTTPStatusError:
                # User doesn't exist, create them
                await client.signup(email, password, name)
            
            clients.append(client)
        
        self._clients = clients
        return clients
    
    async def create_single_user_clients(
        self,
        count: int,
        email: str,
        password: str,
    ) -> List[OpenWebUIClient]:
        """
        Create multiple clients all authenticated as the same user.
        
        This is useful when you want to simulate concurrent connections
        from a single user account (e.g., same user on multiple devices).
        
        Args:
            count: Number of clients to create
            email: Email of the existing user
            password: Password of the existing user
            
        Returns:
            List of authenticated clients (all same user)
            
        Raises:
            httpx.HTTPStatusError: If authentication fails
        """
        clients = []
        
        for i in range(count):
            client = OpenWebUIClient(self.base_url, self.timeout)
            await client.connect()
            
            # Sign in with the same credentials for each client
            await client.signin(email, password)
            clients.append(client)
        
        self._clients = clients
        return clients
    
    async def create_clients_with_existing_users(
        self,
        credentials: List[tuple],
    ) -> List[OpenWebUIClient]:
        """
        Create clients using a list of existing user credentials.
        
        Args:
            credentials: List of (email, password) tuples
            
        Returns:
            List of authenticated clients
            
        Raises:
            httpx.HTTPStatusError: If authentication fails
        """
        clients = []
        
        for email, password in credentials:
            client = OpenWebUIClient(self.base_url, self.timeout)
            await client.connect()
            await client.signin(email, password)
            clients.append(client)
        
        self._clients = clients
        return clients
    
    async def create_benchmark_users(
        self,
        admin_client: OpenWebUIClient,
        count: int,
        email_pattern: str = "benchmark_user_{n}@test.local",
        password: str = "benchmark_pass_123",
        name_pattern: str = "Benchmark User {n}",
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[OpenWebUIClient]:
        """
        Create temporary benchmark users via admin API and authenticate them.
        
        Uses parallel creation for better performance.
        
        This method:
        1. Uses the admin client to create N new users (in parallel batches)
        2. Creates and authenticates a client for each user (in parallel)
        3. Stores user IDs for cleanup later
        
        Args:
            admin_client: Authenticated admin client
            count: Number of users to create
            email_pattern: Email pattern with {n} placeholder
            password: Password for all benchmark users
            name_pattern: Name pattern with {n} placeholder
            progress_callback: Optional callback(current, total) for progress updates
            
        Returns:
            List of authenticated clients for the new users
        """
        self._benchmark_user_ids: List[str] = []
        
        # Create all users in parallel via admin API
        async def create_single_user(index: int) -> Optional[Dict[str, Any]]:
            email = email_pattern.format(n=index + 1)
            name = name_pattern.format(n=index + 1)
            
            try:
                user_data = await admin_client.admin_create_user(
                    email=email,
                    password=password,
                    name=name,
                    role="user",
                )
                return {"index": index, "user_data": user_data, "email": email, "existing": False}
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 400:
                    # User already exists
                    return {"index": index, "user_data": None, "email": email, "existing": True}
                raise
        
        # Create users in parallel (batch to avoid overwhelming the server)
        batch_size = 10
        user_infos = []
        
        for batch_start in range(0, count, batch_size):
            batch_end = min(batch_start + batch_size, count)
            batch_tasks = [create_single_user(i) for i in range(batch_start, batch_end)]
            batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for result in batch_results:
                if isinstance(result, Exception):
                    raise result
                if result:
                    user_infos.append(result)
            
            if progress_callback:
                progress_callback(len(user_infos), count * 2)  # *2 because we also need to auth
        
        # Store user IDs for cleanup
        for info in user_infos:
            if info["user_data"]:
                self._benchmark_user_ids.append(info["user_data"].get("id"))
        
        # Authenticate all users in parallel
        async def auth_user(info: Dict) -> OpenWebUIClient:
            email = info["email"]
            client = OpenWebUIClient(self.base_url, self.timeout)
            await client.connect()
            await client.signin(email, password)
            
            # If user already existed, get their ID for cleanup tracking
            if info["existing"]:
                user_data = await client.get_current_user()
                self._benchmark_user_ids.append(user_data.get("id"))
            
            return client
        
        clients = []
        for batch_start in range(0, len(user_infos), batch_size):
            batch_end = min(batch_start + batch_size, len(user_infos))
            batch_tasks = [auth_user(user_infos[i]) for i in range(batch_start, batch_end)]
            batch_clients = await asyncio.gather(*batch_tasks, return_exceptions=True)
            
            for client in batch_clients:
                if isinstance(client, Exception):
                    raise client
                clients.append(client)
            
            if progress_callback:
                progress_callback(count + len(clients), count * 2)
        
        self._clients = clients
        return clients
    
    async def cleanup_benchmark_users(
        self,
        admin_client: OpenWebUIClient,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        Delete all benchmark users created by create_benchmark_users.
        
        Uses parallel deletion for better performance.
        
        Args:
            admin_client: Authenticated admin client
            progress_callback: Optional callback(current, total) for progress updates
            
        Returns:
            Number of users successfully deleted
        """
        user_ids = getattr(self, '_benchmark_user_ids', [])
        if not user_ids:
            return 0
        
        deleted_count = 0
        batch_size = 10
        
        async def delete_user(user_id: str) -> bool:
            try:
                await admin_client.admin_delete_user(user_id)
                return True
            except httpx.HTTPStatusError:
                return False
        
        for batch_start in range(0, len(user_ids), batch_size):
            batch_end = min(batch_start + batch_size, len(user_ids))
            batch_tasks = [delete_user(user_ids[i]) for i in range(batch_start, batch_end)]
            results = await asyncio.gather(*batch_tasks)
            deleted_count += sum(results)
            
            if progress_callback:
                progress_callback(batch_end, len(user_ids))
        
        self._benchmark_user_ids = []
        return deleted_count
    
    async def close_all(self) -> None:
        """Close all clients in the pool."""
        for client in self._clients:
            await client.close()
        self._clients.clear()
    
    def __len__(self) -> int:
        """Get number of clients in pool."""
        return len(self._clients)
    
    def __iter__(self):
        """Iterate over clients."""
        return iter(self._clients)
    
    def __getitem__(self, index: int) -> OpenWebUIClient:
        """Get client by index."""
        return self._clients[index]
