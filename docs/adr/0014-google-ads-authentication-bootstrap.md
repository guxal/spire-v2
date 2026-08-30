# ADR-0014: Explicit Google Ads authentication bootstrap

## Status

Accepted

## Decision

Google Ads authentication has exactly two production layers:

`GoogleAdsCredentialProvider` owns OAuth refresh-token credentials, access-token
expiry, and the account-scoped temporary token cache. `GoogleAdsClientProvider`
owns normalized Google Ads configuration, normalized `login_customer_id`, and
lazy client construction. No other production module constructs OAuth
credentials or the Google Ads client.

Long-lived bootstrap configuration is the ignored project file
`config/google-ads.yaml`. Temporary access-token metadata is stored only at
`.spire/customers/<customer_id>/cache/google_ads_oauth.json`, atomically and
with owner-only permissions where supported. Authentication is explicit via
the auth CLI; normal capabilities reuse the provider chain automatically.

## Consequences

Status is local-only. Verification performs one harmless customer read. No
refresh-token, access-token, or client secret is printed. The old repository's
OAuth flow and cache expiry/locking behavior are adapted conceptually, while
its loaders, legacy roots, command router, and fallback authentication paths
are not part of v2.
