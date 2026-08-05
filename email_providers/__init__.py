"""
Email providers package for ChatGPT registration tool.
"""

from .common import EmailProvider, EmailProviderError, EmailTimeoutError
from .duckmail import DuckMailProvider
from .yyds import YYDSProvider
from .cloudflare import CloudflareProvider
from .outlook import OutlookProvider
from .cloudflare_temp import CloudflareTempProvider

__all__ = [
    "EmailProvider",
    "EmailProviderError",
    "EmailTimeoutError",
    "DuckMailProvider",
    "YYDSProvider",
    "CloudflareProvider",
    "OutlookProvider",
    "CloudflareTempProvider",
]

# Provider registry
PROVIDERS = {
    "duckmail": DuckMailProvider,
    "mail_tm": DuckMailProvider,  # Same implementation
    "yyds": YYDSProvider,
    "cloudflare": CloudflareProvider,
    "outlook": OutlookProvider,
    "cloudflare_temp": CloudflareTempProvider,
}

def get_provider(name: str, config: dict = None):
    """Get email provider by name."""
    provider_class = PROVIDERS.get(name.lower())
    if not provider_class:
        raise ValueError(f"Unknown email provider: {name}")
    return provider_class(config)
