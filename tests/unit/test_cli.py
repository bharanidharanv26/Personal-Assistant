import importlib

from typer.testing import CliRunner

cli = importlib.import_module("nila.cli.app")
runner = CliRunner()


def test_help_and_version_work_without_server_or_credentials():
    assert runner.invoke(cli.app, ["--help"]).exit_code == 0
    assert "0.1.0" in runner.invoke(cli.app, ["version"]).stdout


def test_approval_requires_confirmation_and_sends_preview_digest(monkeypatch):
    calls = []

    def request(method, path, **kwargs):
        calls.append((method, path, kwargs))
        return {"id": "action", "tool": "dry_run", "digest": "a" * 64}

    monkeypatch.setattr(cli, "request", request)
    rejected = runner.invoke(cli.app, ["action", "approve", "action"], input="n\n")
    assert rejected.exit_code != 0
    assert len(calls) == 1
    accepted = runner.invoke(cli.app, ["action", "approve", "action"], input="y\n")
    assert accepted.exit_code == 0
    assert calls[-1] == (
        "POST", "/actions/action/approve", {"payload": {"digest": "a" * 64}}
    )
