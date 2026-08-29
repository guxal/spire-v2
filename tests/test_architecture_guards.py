from __future__ import annotations

from pathlib import Path


def test_no_legacy_runtime_roots_or_control_plane_package():
    root = Path(__file__).parents[1]
    forbidden = {"data", "actions", "context", "business_memory", "recommendations", "campaign_studio"}
    assert not forbidden.intersection({path.name for path in root.iterdir()})
    assert not (root / "src/spire/control_plane").exists()


def test_reference_repository_is_not_a_runtime_dependency():
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert "spire-agent" not in pyproject


def test_public_campaign_projection_has_no_physical_storage_fields():
    source = (Path(__file__).parents[1] / "src/spire/google_ads/campaigns.py").read_text(
        encoding="utf-8"
    )
    assert "parquet" not in source
    assert "jsonl" not in source
    assert "resource_name" not in source
