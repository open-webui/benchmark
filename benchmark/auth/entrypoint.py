"""
Entrypoint functions for benchmark authentication.

Provides high-level functions to ensure authentication is complete
before any benchmark operations run.
"""

import os
from typing import Optional

from dotenv import load_dotenv

from benchmark.auth.authenticator import Authenticator, AuthResult, AdminCredentials
from benchmark.clients.http_client import OpenWebUIClient


class AuthenticationError(Exception):
    """Raised when authentication fails."""
    pass


class ServiceNotReadyError(Exception):
    """Raised when the Open WebUI service is not reachable."""
    pass


async def ensure_admin_authenticated(
    base_url: Optional[str] = None,
    email: Optional[str] = None,
    password: Optional[str] = None,
    name: Optional[str] = None,
    timeout: float = 30.0,
    wait_for_service: bool = True,
    service_wait_retries: int = 30,
    service_retry_delay: float = 1.0,
) -> tuple[OpenWebUIClient, AuthResult]:
    """
    Ensure admin user is authenticated before running benchmarks.
    
    This is the main entrypoint function that should be called before
    any benchmark operations. It handles:
    
    1. Loading credentials from environment variables (if not provided)
    2. Waiting for the Open WebUI service to be ready
    3. Attempting signin with fallback to signup for first-time setup
    
    Args:
        base_url: Target Open WebUI URL. If None, loads from OPEN_WEBUI_URL
                  or BENCHMARK_TARGET_URL environment variable.
        email: Admin email. If None, loads from ADMIN_USER_EMAIL env var.
        password: Admin password. If None, loads from ADMIN_USER_PASSWORD env var.
        name: Admin display name. If None, loads from ADMIN_USER_NAME or defaults.
        timeout: HTTP request timeout in seconds.
        wait_for_service: Whether to wait for service health check.
        service_wait_retries: Max retries for service health check.
        service_retry_delay: Delay between health check retries.
        
    Returns:
        Tuple of (authenticated OpenWebUIClient, AuthResult)
        
    Raises:
        ServiceNotReadyError: If service is not reachable after retries.
        AuthenticationError: If authentication fails.
        
    Example:
        ```python
        from benchmark.auth import ensure_admin_authenticated
        
        async def run_my_benchmark():
            client, auth_result = await ensure_admin_authenticated()
            
            if auth_result.is_new_signup:
                print("Created new admin account")
            
            # Use authenticated client for benchmark operations
            channels = await client.list_channels()
            ...
        ```
    """
    # Load environment variables
    load_dotenv()
    
    # Resolve base URL
    if base_url is None:
        base_url = os.environ.get(
            "OPEN_WEBUI_URL",
            os.environ.get("BENCHMARK_TARGET_URL", "http://localhost:3000")
        )
    
    # Build credentials
    credentials = None
    if email and password:
        credentials = AdminCredentials(
            email=email,
            password=password,
            name=name or "Admin User",
        )
    # Otherwise, Authenticator will load from env
    
    # Create authenticator
    authenticator = Authenticator(base_url, timeout)
    
    try:
        # Wait for service to be ready
        if wait_for_service:
            is_ready = await authenticator.wait_for_service(
                max_retries=service_wait_retries,
                retry_delay=service_retry_delay,
            )
            if not is_ready:
                await authenticator.close()
                raise ServiceNotReadyError(
                    f"Open WebUI service at {base_url} is not ready after "
                    f"{service_wait_retries} attempts."
                )
        
        # Authenticate admin
        result = await authenticator.authenticate_admin(credentials)
        
        if not result.success:
            await authenticator.close()
            raise AuthenticationError(result.error)
        
        # Return the client (don't close - caller owns it now)
        return result.client, result
        
    except (ServiceNotReadyError, AuthenticationError):
        # Re-raise our custom exceptions
        raise
    except Exception as e:
        await authenticator.close()
        raise AuthenticationError(f"Unexpected error during authentication: {e}")


async def check_auth_status(
    base_url: Optional[str] = None,
    timeout: float = 10.0,
) -> dict:
    """
    Check authentication configuration and service status.
    
    Useful for validating environment setup before running benchmarks.
    Does not perform actual authentication.
    
    Args:
        base_url: Target Open WebUI URL. If None, loads from environment.
        timeout: HTTP request timeout in seconds.
        
    Returns:
        Dictionary with status information:
        - service_url: The resolved service URL
        - service_reachable: Whether health endpoint responds
        - credentials_configured: Whether admin credentials are in environment
        - admin_email: The configured admin email (if set)
    """
    load_dotenv()
    
    # Resolve base URL
    if base_url is None:
        base_url = os.environ.get(
            "OPEN_WEBUI_URL",
            os.environ.get("BENCHMARK_TARGET_URL", "http://localhost:3000")
        )
    
    # Check credentials
    credentials = AdminCredentials.from_env()
    
    # Check service health
    service_reachable = False
    try:
        authenticator = Authenticator(base_url, timeout)
        service_reachable = await authenticator.wait_for_service(
            max_retries=3,
            retry_delay=1.0,
        )
        await authenticator.close()
    except Exception:
        pass
    
    return {
        "service_url": base_url,
        "service_reachable": service_reachable,
        "credentials_configured": credentials is not None,
        "admin_email": credentials.email if credentials else None,
    }
