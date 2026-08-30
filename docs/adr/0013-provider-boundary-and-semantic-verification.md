# ADR-0013: Validate, send, and verify through one provider lifecycle

## Status

Accepted

## Decision

Production operations are accepted by Google Ads with `validate_only=true`
before approval. After exact local approval checks, the previously compiled
operation is sent without rebuilding or an extra live pre-dispatch read.
`request_sent` is persisted before transport. An ambiguous result after that
point is `RECONCILING` and is never blindly retried. A successful provider
response is insufficient: semantic read-back must prove the requested state.

Validate-only, mutation, and read-back share one injected lazy
`GoogleAdsClientProvider`; client construction has one owner.
