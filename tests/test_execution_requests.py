from spire.execution.requests import normalize_search_campaign_request


def test_search_campaign_request_is_typed_and_deterministic():
    request = {
        "campaign_name": "  Search  Test ",
        "daily_budget": "10.00",
        "geo_target_ids": ["2170", "2170"],
        "language_criterion_ids": ["1003"],
        "bidding_strategy": "maximize_clicks",
        "ad_groups": [
            {
                "name": " Core ",
                "keywords": [{"text": " roof repair ", "match_type": "phrase"}],
                "headlines": ["Roof repair", "Local roofers", "Request a quote"],
                "descriptions": ["Professional roof repair.", "Request a local quote today."],
                "final_url": "https://example.test/roof-repair",
            }
        ],
    }

    normalized = normalize_search_campaign_request(request)

    assert normalized["campaign_name"] == "Search Test"
    assert normalized["daily_budget"] == "10"
    assert normalized["geo_target_ids"] == ("2170",)
    assert normalized["bidding_strategy"] == "MAXIMIZE_CLICKS"
    assert normalized["ad_groups"][0]["keywords"] == ({"text": "roof repair", "match_type": "PHRASE"},)
