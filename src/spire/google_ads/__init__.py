"""Google Ads provider, discovery, and explicit refresh services."""

from .auth import run_installed_app_oauth, write_google_ads_config
from .campaigns import CampaignReadService
from .config import GoogleAdsConfig, normalize_login_customer_id
from .discovery import AccountDiscoveryService, DiscoveryResult
from .extraction import RefreshResult, RefreshSpec, ScopedRefreshService
from .provider import GoogleAdsClientProvider

__all__ = [
    "AccountDiscoveryService",
    "CampaignReadService",
    "DiscoveryResult",
    "GoogleAdsClientProvider",
    "GoogleAdsConfig",
    "RefreshResult",
    "RefreshSpec",
    "ScopedRefreshService",
    "normalize_login_customer_id",
    "run_installed_app_oauth",
    "write_google_ads_config",
]
