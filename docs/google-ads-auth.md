# Google Ads Authentication

## Prerequisites

- Google Ads developer token
- Google Cloud OAuth client for an installed application
- A Google account with access to the Google Ads account
- A login customer / manager ID when the account requires one

## First-time setup

From the repository root:

```text
python -m pip install -e ".[dev]"
cp config/google-ads.example.yaml config/google-ads.yaml
```

Edit `config/google-ads.yaml` with the developer token, OAuth client ID,
OAuth client secret, and login customer ID. Then run:

```text
spire auth google-ads login
```

The command opens the installed-app OAuth flow in a browser, obtains a
long-lived `refresh_token`, and writes it to the private config file. It does
not print secrets and refuses to replace an existing refresh token silently.

## Login

`spire auth google-ads login` is for first-time setup. It uses the client
configuration already in `config/google-ads.yaml`; it does not contact Google
Ads to discover an account.

## Verify authentication

Run one harmless authenticated Google Ads read:

```text
spire auth google-ads verify --customer-id 1234567890
```

Expected output is concise and secret-free:

```text
authentication: OK
customer_access: OK
customer_id: 1234567890
login_customer_id: 1234567890
oauth_refresh_performed: YES
token_cache: MISS
```

`verify` performs no mutation.

## Authentication lifecycle

```text
refresh_token → access_token → token cache → GoogleAdsClient
```

The `GoogleAdsCredentialProvider` creates OAuth credentials, reuses a valid
cached access token, and refreshes it when it is missing or near expiry. The
`GoogleAdsClientProvider` then constructs one lazy client for its lifecycle.
Discovery, account refresh, validate-only, mutation, and semantic read-back
all receive this same provider chain.

## Token cache

The access token is temporary. Spire stores only the token and its expiry at:

```text
.spire/customers/<customer_id>/cache/google_ads_oauth.json
```

The cache is account-scoped, ignored by Git, written atomically, protected by
a file lock, and set to mode `0600` where supported. A usable token is reused
without contacting `accounts.google.com`; an expired or missing token is
refreshed with the long-lived refresh token and atomically replaces the cache.

## Credential locations

Long-lived configuration:

```text
config/google-ads.yaml
```

Use the committed template at `config/google-ads.example.yaml`. The real file
is ignored by Git and written with owner-only permissions. Do not put secrets
in `truth/`, `knowledge/`, `execution/`, or the account cache.

Temporary access-token cache:

```text
.spire/customers/<customer_id>/cache/google_ads_oauth.json
```

`WorkspacePaths` derives the account cache root; no other runtime root is
consulted.

## Security

- Never commit `config/google-ads.yaml` or share its contents.
- Never share a refresh token, client secret, or access token.
- Keep credential and cache files owner-readable only.
- Secrets never appear in CLI output, exception messages, or logs.
- `status` is local-only and never calls Google services.

## Troubleshooting

`AUTH_NOT_CONFIGURED`
: Copy the example file, fill the required fields, and complete login.

`OAUTH_REFRESH_FAILED`
: Repeat login after checking the OAuth client, consent, and refresh-token
  validity. The token value is intentionally not shown.

`PROVIDER_UNAVAILABLE`
: Check network access and Google API availability, then retry a read.

`CUSTOMER_ACCESS_DENIED`
: Confirm the signed-in Google account can access the customer and that the
  customer ID is correct.

`INVALID_LOGIN_CUSTOMER`
: Use the numeric login or manager customer ID; hyphens are normalized.

`INVALID_CREDENTIAL_CONFIG`
: Check that the YAML is a mapping and contains the required bootstrap fields.
