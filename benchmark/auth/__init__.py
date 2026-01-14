"""
Authentication module for Open WebUI Benchmark.

Provides consistent authentication handling across all benchmark scripts.
"""

from benchmark.auth.authenticator import Authenticator, AuthResult
from benchmark.auth.entrypoint import (
    ensure_admin_authenticated,
    AuthenticationError,
    ServiceNotReadyError,
)

__all__ = [
    "Authenticator",
    "AuthResult",
    "ensure_admin_authenticated",
    "AuthenticationError",
    "ServiceNotReadyError",
]
