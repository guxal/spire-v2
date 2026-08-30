from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_public_adapters_do_not_construct_google_clients_or_read_storage():
    cli_sources = list((ROOT / "src" / "spire" / "cli_commands").glob("*.py"))
    cli_sources.append(ROOT / "src" / "spire" / "cli.py")
    mcp_source = ROOT / "src" / "spire" / "mcp_server.py"
    public_text = "\n".join(path.read_text(encoding="utf-8") for path in [*cli_sources, mcp_source])
    assert "GoogleAdsClient" not in public_text
    assert "DatasetResolver" not in public_text
    assert ".parquet" not in public_text
    assert "approve_run" not in public_text


def test_mcp_tool_inventory_has_no_authority_creation_surface():
    from spire.mcp_server import TOOLS

    names = {name for name, _description, _schema in TOOLS}
    assert names.isdisjoint({"approve_run", "grant_authority", "mint_approval"})
