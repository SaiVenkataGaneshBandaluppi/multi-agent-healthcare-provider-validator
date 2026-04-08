"""
MIT License
SlowAPI rate limiter configuration.
"""
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def standard_limit(request, response=None):
    """60 requests per minute for standard endpoints."""
    return "60/minute"


def validation_limit(request, response=None):
    """10 requests per minute for validation endpoints."""
    return "10/minute"
