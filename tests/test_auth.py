import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import monofact.auth as auth_mod
import monofact.cli as cli_mod
from monofact.auth import inspect_auth, resolve_auth_credentials
from monofact.cli import main
from monofact.config import load_settings


def _make_pyafipws_profile(tmp_path: Path, profile_name: str) -> Path:
    root = tmp_path / "pyafipws"
    conf = root / "conf"
    cache = root / "cache"
    conf.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    (conf / f"{profile_name}.crt").write_text("dummy crt")
    (conf / f"{profile_name}.key").write_text("dummy key")
    (conf / f"{profile_name}.ini").write_text(
        "\n".join(
            [
                "[WSAA]",
                f"CERT = conf/{profile_name}.crt",
                f"PRIVATEKEY = conf/{profile_name}.key",
                "URL = https://example.test/wsaa",
                "CACERT = default",
            ]
        )
    )
    return root


def test_inspect_auth_uses_pyafipws_profile_when_tokens_absent(tmp_path):
    pyafipws_dir = _make_pyafipws_profile(tmp_path, "homologacion")
    settings = load_settings(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        token="",
        sign="",
        pyafipws_dir=str(pyafipws_dir),
    )

    assert inspect_auth(settings) == ("pyafipws", "homologacion")


def test_resolve_auth_credentials_uses_wsaa_from_pyafipws(monkeypatch, tmp_path):
    pyafipws_dir = _make_pyafipws_profile(tmp_path, "produccion")
    settings = load_settings(
        env="prod",
        cuit=20123456789,
        pto_vta=1,
        token="",
        sign="",
        pyafipws_dir=str(pyafipws_dir),
    )

    class FakeWSAA:
        def __init__(self):
            self.Token = ""
            self.Sign = ""
            self.calls = []

        def Autenticar(self, *args, **kwargs):
            self.calls.append((args, kwargs))
            self.Token = "tok_prod"
            self.Sign = "sig_prod"

        def ObtenerTagXml(self, tag):
            assert tag == "expirationTime"
            return "2026-03-21T02:12:07-03:00"

    monkeypatch.setattr(auth_mod, "_get_wsaa_class", lambda: FakeWSAA)

    creds = resolve_auth_credentials(settings)

    assert creds.token == "tok_prod"
    assert creds.sign == "sig_prod"
    assert creds.source == "pyafipws"
    assert creds.profile_name == "produccion"
    assert creds.expiration_time == "2026-03-21T02:12:07-03:00"
    assert creds.ta_path is not None
    assert creds.ta_path.name.startswith("TA-")


def test_auth_refresh_command_returns_profile_metadata(monkeypatch, tmp_path):
    monkeypatch.setattr(
        cli_mod,
        "load_pyafipws_profile",
        lambda settings: SimpleNamespace(profile_name="homologacion"),
    )
    monkeypatch.setattr(
        cli_mod,
        "resolve_auth_credentials",
        lambda settings, force_refresh=False: SimpleNamespace(
            ta_path=tmp_path / "pyafipws" / "cache" / "TA-test.xml",
            expiration_time="2026-03-21T05:51:48-03:00",
        ),
    )

    runner = CliRunner()
    res = runner.invoke(main, ["auth-refresh", "--env", "homo"])

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] is True
    assert data["env"] == "homo"
    assert data["profile"] == "homologacion"
    assert data["ta_path"].endswith("TA-test.xml")
