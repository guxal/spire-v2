from __future__ import annotations

import json

from spire.core import WorkspacePaths
from spire.google_ads import (
    AccountDiscoveryService,
    CampaignReadService,
    GoogleAdsClientProvider,
    RefreshSpec,
    ScopedRefreshService,
)
from spire.truth import AccountSnapshotService, DatasetResolver


def test_clean_account_bootstrap_from_zero(tmp_path, campaign_rows):
    customer_id = "1234567890"
    assert not (tmp_path / ".spire/customers" / customer_id).exists()
    config_path = tmp_path / "google-ads.yaml"
    config_path.write_text(
        json.dumps({"developer_token": "test-token", "login_customer_id": "123-456-7890"}),
        encoding="utf-8",
    )
    calls: list[str] = []

    from conftest import FakeClient

    client = FakeClient(campaign_rows, calls)
    provider = GoogleAdsClientProvider(config_path, client_factory=lambda _: client)
    workspace = WorkspacePaths(tmp_path)
    discovery = AccountDiscoveryService(provider, workspace)
    refresh = ScopedRefreshService(provider, workspace)
    reads = CampaignReadService(discovery, AccountSnapshotService(workspace))

    assert not calls
    reads.discover(customer_id)
    result = refresh.refresh(RefreshSpec(customer_id, ("101",)))
    snapshot = AccountSnapshotService(workspace).current(customer_id)
    campaign = reads.get(customer_id, "101")

    assert snapshot.extraction_id == result.extraction_id
    assert DatasetResolver(workspace, customer_id).resolve_dataset(
        snapshot.extraction_id, "campaigns"
    ).rows[0]["campaign_id"] == "101"
    assert campaign["name"] == "Search - Brand"
    assert campaign["daily_budget"] == 12.5
    assert len(calls) == 22
    assert (workspace.truth(customer_id) / "current.json").exists()
    assert not any(
        (tmp_path / name).exists()
        for name in ("data", "actions", "context", "business_memory", "recommendations", "campaign_studio")
    )
