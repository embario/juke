"""Compatibility for provider failures across social-auth-core 5.x and 6.x."""

try:
    from social_core.exceptions import AuthProviderError as AuthConnectionError
except ImportError:  # social-auth-core < 6
    from social_core.exceptions import AuthConnectionError

__all__ = ['AuthConnectionError']
