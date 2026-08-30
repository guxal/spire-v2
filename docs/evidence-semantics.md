# Evidence aggregation semantics

`spire evidence query` and the MCP `evidence_query` tool return frozen evidence
from the current certified refresh. Every response includes a `semantics` object
with these fields:

- `coverage`: what rows the Google Ads view can represent;
- `attribution_scope`: what Google Ads attributes to those rows;
- `aggregation_semantics`: how rows may be combined safely;
- `limitations`: known reasons the view can be partial or non-additive;
- `comparison_baseline`: the dataset to use as the campaign control total.

Use `campaign_daily` as the canonical campaign performance baseline. Do not
force segmented datasets to equal it:

- `search_terms` can omit queries because of privacy and volume thresholds;
- `keyword_daily` excludes non-keyword targeting and removed criteria;
- `geo_daily` includes only reportable geographic classifications;
- ad and asset performance views can omit zero-metric entities;
- asset rows can overlap when several assets serve in the same ad;
- Auction Insights contains distinct `CAMPAIGN_SUMMARY` and
  `AUCTION_PARTICIPANT` row types, and share metrics across rows are unweighted
  arithmetic means. When Google Ads restricts participant metrics, a
  `PARTICIPANT_AVAILABILITY` row records the limitation and the campaign summary
  remains available; no participant domain is inferred.

Structural coverage remains available in `campaign_ads` and
`campaign_assets`. Performance is exposed separately in `ad_performance`,
`campaign_asset_performance`, and `rsa_asset_performance`. Always preserve the
response's logical `evidence_ref`; no physical storage knowledge is required.
