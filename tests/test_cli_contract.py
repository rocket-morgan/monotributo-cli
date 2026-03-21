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
        return 123

    def emit_factura_c(self, req):
        if self.token == "reject":
            return {
                "ok": False,
                "resultado": "R",
                "cbte_nro": 124,
                "cae": "",
                "cae_vto": "",
                "obs": [{"code": 1001, "msg": "obs"}],
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

    def get_invoice_detail(self, tipo_comp, pto_vta, cbte_nro):
        if self.token == "detail-fail":
            raise RuntimeError("fallo detail")
        return {
            "tipo_comp": tipo_comp,
            "pto_vta": pto_vta,
            "cbte_nro": cbte_nro,
            "resultado": "A",
            "cae": "12345678901234",
            "cae_vto": "20260331",
            "emision_tipo": "CAE",
            "obs": [],
            "errors": [],
            "invoice": {
                "tipo_cbte": tipo_comp,
                "punto_vta": pto_vta,
                "cbt_hasta": cbte_nro,
            },
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
        "MONOFACT_PYAFIPWS_DIR": str(tmp_path / "missing_pyafipws"),
    }


def test_contract_invoice_create_success_keys(monkeypatch, tmp_path):
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
    assert res.exit_code == 0

    data = json.loads(res.output)
    expected_keys = {
        "ok",
        "resultado",
        "cbte_nro",
        "cae",
        "cae_vto",
        "obs",
        "errors",
        "fingerprint",
        "record_id",
    }
    assert set(data.keys()) == expected_keys
    assert isinstance(data["ok"], bool)
    assert isinstance(data["cbte_nro"], int)
    assert isinstance(data["cae"], str)
    assert isinstance(data["record_id"], int)


def test_contract_invoice_create_rejected_keys(monkeypatch, tmp_path):
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
    assert res.exit_code == 4

    data = json.loads(res.output)
    expected_keys = {
        "ok",
        "resultado",
        "cbte_nro",
        "cae",
        "cae_vto",
        "obs",
        "errors",
        "fingerprint",
        "record_id",
    }
    assert set(data.keys()) == expected_keys
    assert data["ok"] is False
    assert data["resultado"] == "R"
    assert isinstance(data["errors"], list)


def test_contract_invoice_last_shape(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    res = runner.invoke(main, ["invoice-last"], env=_base_env(tmp_path))

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "last", "tipo_comp", "pto_vta"}
    assert data["ok"] is True
    assert isinstance(data["last"], int)


def test_contract_config_check_shape(tmp_path):
    runner = CliRunner()
    res = runner.invoke(main, ["config-check"], env=_base_env(tmp_path))

    assert res.exit_code == 0
    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "env", "cuit", "pto_vta", "wsfe_url"}
    assert data["ok"] is True


def test_contract_validation_error_shape(tmp_path):
    runner = CliRunner()
    env = {
        "MONOFACT_ENV": "homo",
        "MONOFACT_CUIT": "0",
        "MONOFACT_PTO_VTA": "0",
        "MONOFACT_TOKEN": "",
        "MONOFACT_SIGN": "",
        "MONOFACT_DB_PATH": str(tmp_path / "monofact.db"),
        "MONOFACT_PYAFIPWS_DIR": str(tmp_path / "missing_pyafipws"),
    }
    res = runner.invoke(main, ["config-check"], env=env)

    assert res.exit_code == 2
    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "error_type", "errors"}
    assert data["error_type"] == "validation"
    assert isinstance(data["errors"], list)


def test_contract_invoice_create_validation_error_shape(tmp_path):
    runner = CliRunner()
    env = _base_env(tmp_path)
    env["MONOFACT_CUIT"] = "0"

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
        ],
        env=env,
    )

    assert res.exit_code == 2
    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "error_type", "errors"}
    assert data["error_type"] == "validation"
    assert isinstance(data["errors"], list)


def test_contract_invoice_list_shape(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)
    runner.invoke(
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

    res = runner.invoke(main, ["invoice-list", "--cbte-nro", "124"], env=env)
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "count", "env", "pto_vta", "tipo_comp", "filters", "items"}
    assert data["ok"] is True
    assert isinstance(data["count"], int)
    assert isinstance(data["items"], list)


def test_contract_invoice_show_shape(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)
    runner.invoke(
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

    res = runner.invoke(main, ["invoice-show", "--cbte-nro", "124"], env=env)
    assert res.exit_code == 0

    data = json.loads(res.output)
    assert set(data.keys()) == {"ok", "source", "local_fallback", "env", "pto_vta", "tipo_comp", "cbte_nro", "afip", "local"}
    assert data["ok"] is True
