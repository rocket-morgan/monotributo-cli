import json
from pathlib import Path
from types import SimpleNamespace

from click.testing import CliRunner

import monofact.auth as auth_mod
import monofact.cli as cli_mod
from monofact.auth import inspect_auth, resolve_auth_credentials
from monofact.cli import main
from monofact.config import _load_dotenv_once, load_settings


def _clear_monofact_env(monkeypatch):
    for key in [
        "MONOFACT_ENV",
        "MONOFACT_CUIT",
        "MONOFACT_PTO_VTA",
        "MONOFACT_TIPO_COMP_FACTURA_C",
        "MONOFACT_TOKEN",
        "MONOFACT_SIGN",
        "MONOFACT_DB_PATH",
        "MONOFACT_PYAFIPWS_DIR",
        "MONOFACT_WSFE_HOMO",
        "MONOFACT_WSFE_PROD",
    ]:
        monkeypatch.delenv(key, raising=False)


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


def test_path_like_token_and_sign_fall_back_to_pyafipws(monkeypatch, tmp_path):
    pyafipws_dir = _make_pyafipws_profile(tmp_path, "homologacion")
    token_file = tmp_path / "token.txt"
    sign_file = tmp_path / "sign.txt"
    token_file.write_text("not-a-real-token")
    sign_file.write_text("not-a-real-sign")

    settings = load_settings(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        token=str(token_file),
        sign=str(sign_file),
        pyafipws_dir=str(pyafipws_dir),
    )

    assert inspect_auth(settings) == ("pyafipws", "homologacion")


def test_config_check_autoloads_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_monofact_env(monkeypatch)
    _load_dotenv_once.cache_clear()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MONOFACT_ENV=homo",
                "MONOFACT_CUIT=20123456789",
                "MONOFACT_PTO_VTA=2",
                "MONOFACT_PYAFIPWS_DIR=" + str(_make_pyafipws_profile(tmp_path, "homologacion")),
            ]
        )
    )

    runner = CliRunner()
    res = runner.invoke(main, ["config-check"], env={})

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["ok"] is True
    assert data["cuit"] == 20123456789
    assert data["pto_vta"] == 2


def test_shell_env_overrides_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_monofact_env(monkeypatch)
    _load_dotenv_once.cache_clear()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MONOFACT_ENV=homo",
                "MONOFACT_CUIT=11111111111",
                "MONOFACT_PTO_VTA=7",
                "MONOFACT_PYAFIPWS_DIR=" + str(_make_pyafipws_profile(tmp_path, "homologacion")),
            ]
        )
    )

    runner = CliRunner()
    res = runner.invoke(
        main,
        ["config-check"],
        env={
            "MONOFACT_CUIT": "20123456789",
            "MONOFACT_PTO_VTA": "2",
        },
    )

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["cuit"] == 20123456789
    assert data["pto_vta"] == 2


def test_flags_override_shell_and_dotenv(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _clear_monofact_env(monkeypatch)
    _load_dotenv_once.cache_clear()
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MONOFACT_ENV=homo",
                "MONOFACT_CUIT=11111111111",
                "MONOFACT_PTO_VTA=7",
                "MONOFACT_PYAFIPWS_DIR=" + str(_make_pyafipws_profile(tmp_path, "homologacion")),
            ]
        )
    )

    runner = CliRunner()
    res = runner.invoke(
        main,
        ["config-check", "--cuit", "20123456789", "--pto-vta", "2"],
        env={
            "MONOFACT_CUIT": "29999999999",
            "MONOFACT_PTO_VTA": "9",
        },
    )

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert data["cuit"] == 20123456789
    assert data["pto_vta"] == 2
