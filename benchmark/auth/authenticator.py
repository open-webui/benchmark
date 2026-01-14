"""
Authenticator class for Open WebUI.

Encapsulates the signin-with-fallback-to-signup pattern for admin users.
"""

import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from benchmark.clients.http_client import OpenWebUIClient, User


@dataclass
class AuthResult:
    """Result of an authentication attempt."""
    success: bool
    user: Optional[User] = None
    client: Optional[OpenWebUIClient] = None
    error: Optional[str] = None
    is_new_signup: bool = False


@dataclass
class AdminCredentials:
    """Admin user credentials loaded from environment."""
    email: str
    password: str
    name: str = "Admin User"
    
    @classmethod
    def from_env(cls) -> Optional["AdminCredentials"]:
        """
        Load admin credentials from environment variables.
        
        Looks for:
        - ADMIN_USER_EMAIL
        - ADMIN_USER_PASSWORD
        - ADMIN_USER_NAME (optional, defaults to "Admin User")
        
        Returns:
            AdminCredentials if both email and password are set, None otherwise.
        """
        load_dotenv()
        
        email = os.environ.get("ADMIN_USER_EMAIL")
        password = os.environ.get("ADMIN_USER_PASSWORD")
        name = os.environ.get("ADMIN_USER_NAME", "Admin User")
        
        if email and password:
            return cls(email=email, password=password, name=name)
        return None


class Authenticator:
    """
    Handles authentication to Open WebUI instances.
    
    Provides a consistent signin-with-fallback-to-signup pattern
    for admin user authentication.
    """
    
    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ):
        """
        Initialize the authenticator.
        
        Args:
            base_url: Base URL of the Open WebUI instance
            timeout: Request timeout in seconds
        """
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client: Optional[OpenWebUIClient] = None
        self._authenticated_user: Optional[User] = None
    
    @property
    def client(self) -> Optional[OpenWebUIClient]:
        """Get the authenticated client."""
        return self._client
    
    @property
    def user(self) -> Optional[User]:
        """Get the authenticated user."""
        return self._authenticated_user
    
    @property
    def token(self) -> Optional[str]:
        """Get the authentication token."""
        if self._authenticated_user:
            return self._authenticated_user.token
        return None
    
    @property
    def is_authenticated(self) -> bool:
        """Check if currently authenticated."""
        return self._authenticated_user is not None
    
    async def _create_client(self) -> OpenWebUIClient:
        """Create and connect an HTTP client."""
        client = OpenWebUIClient(self.base_url, self.timeout)
        await client.connect()
        return client
    
    async def wait_for_service(
        self,
        max_retries: int = 30,
        retry_delay: float = 1.0,
    ) -> bool:
        """
        Wait for the Open WebUI service to be ready.
        
        Args:
            max_retries: Maximum number of health check attempts
            retry_delay: Delay between retries in seconds
            
        Returns:
            True if service is ready, False otherwise
        """
        if self._client is None:
            self._client = await self._create_client()
        
        # Convert to timeout/interval format expected by wait_for_ready
        timeout = max_retries * retry_delay
        return await self._client.wait_for_ready(
            timeout=timeout,
            interval=retry_delay,
        )
    
    async def authenticate_admin(
        self,
        credentials: Optional[AdminCredentials] = None,
    ) -> AuthResult:
        """
        Authenticate as admin user using signin with fallback to signup.
        
        If the admin user doesn't exist (first run), creates the account.
        If the admin user exists, signs in with provided credentials.
        
        Args:
            credentials: Admin credentials. If None, loads from environment.
            
        Returns:
            AuthResult with authentication status and user details.
        """
        # Load credentials from environment if not provided
        if credentials is None:
            credentials = AdminCredentials.from_env()
        
        if credentials is None:
            return AuthResult(
                success=False,
                error=(
                    "Admin credentials not configured. "
                    "Set ADMIN_USER_EMAIL and ADMIN_USER_PASSWORD environment variables."
                ),
            )
        
        # Create client if needed
        if self._client is None:
            self._client = await self._create_client()
        
        # Try signin first (existing user)
        is_new_signup = False
        try:
            user = await self._client.signin(credentials.email, credentials.password)
            self._authenticated_user = user
            return AuthResult(
                success=True,
                user=user,
                client=self._client,
                is_new_signup=False,
            )
        except Exception as signin_error:
            # Signin failed - try signup (new instance, first admin)
            try:
                user = await self._client.signup(
                    credentials.email,
                    credentials.password,
                    credentials.name,
                )
                self._authenticated_user = user
                return AuthResult(
                    success=True,
                    user=user,
                    client=self._client,
                    is_new_signup=True,
                )
            except Exception as signup_error:
                return AuthResult(
                    success=False,
                    error=(
                        f"Failed to authenticate admin user ({credentials.email}). "
                        f"Signin error: {signin_error}. Signup error: {signup_error}"
                    ),
                )
    
    async def close(self) -> None:
        """Close the client connection."""
        if self._client:
            await self._client.close()
            self._client = None
        self._authenticated_user = None
    
    async def __aenter__(self) -> "Authenticator":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()
