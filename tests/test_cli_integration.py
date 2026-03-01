import json
from pathlib import Path

from click.testing import CliRunner

from monofact.cli import main


class FakeAFIPAdapter:
    def __init__(self, wsfe_url, cuit, token, sign, cache="./cache"):
        self.wsfe_url = wsfe_url
        self.cuit = cuit
        self.token = token
        self.sign = sign

    def get_last_cbte(self, tipo_comp, pto_vta):
        if self.token == "boom":
            raise RuntimeError("fallo transporte")
        return 123

    def emit_factura_c(self, req):
        if self.token == "reject":
            return {
                "ok": False,
                "resultado": "R",
                "cbte_nro": 124,
                "cae": "",
                "cae_vto": "",
                "obs": [],
                "errors": ["10000: rechazo"],
                "fingerprint": "f" * 64,
            }
        return {
            "ok": True,
            "resultado": "A",
            "cbte_nro": 124,
            "cae": "12345678901234",
            "cae_vto": "20260331",
            "obs": [],
            "errors": [],
            "fingerprint": "f" * 64,
        }


def _base_env(tmp_path: Path):
    return {
        "MONOFACT_ENV": "homo",
        "MONOFACT_CUIT": "20123456789",
        "MONOFACT_PTO_VTA": "1",
        "MONOFACT_TIPO_COMP_FACTURA_C": "11",
        "MONOFACT_TOKEN": "token_ok",
        "MONOFACT_SIGN": "sign_ok",
        "MONOFACT_DB_PATH": str(tmp_path / "monofact.db"),
    }


def test_config_check_ok(monkeypatch, tmp_path):
    env = _base_env(tmp_path)
    runner = CliRunner()
    res = runner.invoke(main, ["config-check"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["ok"] is True
    assert data["cuit"] == 20123456789


def test_config_check_validation_error(tmp_path):
    runner = CliRunner()
    env = {
        "MONOFACT_ENV": "homo",
        "MONOFACT_CUIT": "0",
        "MONOFACT_PTO_VTA": "0",
        "MONOFACT_TOKEN": "",
        "MONOFACT_SIGN": "",
        "MONOFACT_DB_PATH": str(tmp_path / "monofact.db"),
    }
    res = runner.invoke(main, ["config-check"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["ok"] is False
    assert data["error_type"] == "validation"


def test_invoice_last_ok(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    res = runner.invoke(main, ["invoice-last"], env=_base_env(tmp_path))
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["ok"] is True
    assert data["last"] == 123


def test_invoice_create_ok_persists(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "96",
            "--doc-nro",
            "12345678",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            "20260301",
        ],
        env=_base_env(tmp_path),
    )
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["ok"] is True
    assert data["cae"] == "12345678901234"
    assert data["record_id"] >= 1


def test_invoice_create_rejected(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    env = _base_env(tmp_path)
    env["MONOFACT_TOKEN"] = "reject"

    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "96",
            "--doc-nro",
            "12345678",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            "20260301",
        ],
        env=env,
    )
    data = json.loads(res.output)

    assert res.exit_code == 4
    assert data["ok"] is False
    assert data["resultado"] == "R"


def test_invoice_create_validation_error(tmp_path):
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "96",
            "--doc-nro",
            "12345678",
            "--imp-total",
            "0",
        ],
        env=_base_env(tmp_path),
    )
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["ok"] is False
    assert data["error_type"] == "validation"


def test_invoice_last_unexpected_error(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    env = _base_env(tmp_path)
    env["MONOFACT_TOKEN"] = "boom"

    runner = CliRunner()
    res = runner.invoke(main, ["invoice-last"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 5
    assert data["ok"] is False
    assert data["error_type"] == "unexpected"
