---
type: adr
decision: ADR-0007
domain: google-ads
status: accepted
---

# ADR-0007 — One lazy Google Ads client provider owns auth construction

`GoogleAdsClientProvider` owns one normalized `GoogleAdsConfig`, one normalized
`login_customer_id`, and one lazily constructed client for its lifecycle.
Services receive the provider or its client; they do not load YAML, build
credentials, or duplicate `load_client` behavior. Constructing a provider or a
service performs no network/client construction.

OAuth behavior remains the installed-app flow used by the reference system;
this ADR only places ownership behind the v2 provider boundary.
