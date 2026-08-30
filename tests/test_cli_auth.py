from pathlib import Path

from spire.cli import main


def test_status_cli_is_local_and_secret_free(tmp_path, capsys):
    assert main(["--project-root", str(tmp_path), "auth", "google-ads", "status"]) == 0
    output = capsys.readouterr().out
    assert "configured: NO" in output
    assert "refresh_token: MISSING" in output
    assert "refresh-secret" not in output


def test_example_config_and_gitignore_protect_auth_state():
    root = Path(__file__).parents[1]
    example = (root / "config/google-ads.example.yaml").read_text(encoding="utf-8")
    ignored = (root / ".gitignore").read_text(encoding="utf-8")
    assert "REPLACE_WITH" in example
    assert "refresh-secret" not in example
    assert "config/google-ads.yaml" in ignored
    assert ".spire/customers/*/cache/google_ads_oauth.json" in ignored
