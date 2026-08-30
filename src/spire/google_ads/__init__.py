"""Google Ads provider, discovery, and explicit refresh services."""

from .auth import run_installed_app_oauth, write_google_ads_config
from .auth_service import GoogleAdsAuthService
from .campaigns import CampaignReadService
from .config import GoogleAdsConfig, default_google_ads_config_path, normalize_login_customer_id
from .credentials import GoogleAdsCredentialProvider, google_ads_token_cache_path
from .discovery import AccountDiscoveryService, DiscoveryResult
from .extraction import RefreshResult, RefreshSpec, ScopedRefreshService
from .provider import GoogleAdsClientProvider

__all__ = [
    "AccountDiscoveryService",
    "CampaignReadService",
    "DiscoveryResult",
    "GoogleAdsAuthService",
    "GoogleAdsClientProvider",
    "GoogleAdsConfig",
    "GoogleAdsCredentialProvider",
    "RefreshResult",
    "RefreshSpec",
    "ScopedRefreshService",
    "default_google_ads_config_path",
    "google_ads_token_cache_path",
    "normalize_login_customer_id",
    "run_installed_app_oauth",
    "write_google_ads_config",
]
