import datetime as dt
import json
import sqlite3
from pathlib import Path

import yaml
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

    def get_invoice_detail(self, tipo_comp, pto_vta, cbte_nro):
        if self.token in {"boom", "detail-fail"}:
            raise RuntimeError("fallo transporte" if self.token == "boom" else "fallo detail")
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


def _create_invoice(runner: CliRunner, env: dict[str, str], *, doc_tipo: str = "96", cbte_fch: str = "20260301"):
    return runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            doc_tipo,
            "--doc-nro",
            "12345678" if doc_tipo != "consumidor-final" else "0",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            cbte_fch,
        ],
        env=env,
    )


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
        "MONOFACT_PYAFIPWS_DIR": str(tmp_path / "missing_pyafipws"),
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


def test_invoice_last_yaml_success(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    res = runner.invoke(main, ["--format", "yaml", "invoice-last"], env=_base_env(tmp_path))
    data = yaml.safe_load(res.output)

    assert res.exit_code == 0
    assert data["ok"] is True
    assert data["last"] == 123


def test_invoice_create_ok_persists(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    res = _create_invoice(runner, _base_env(tmp_path))
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
    res = _create_invoice(runner, env)
    data = json.loads(res.output)

    assert res.exit_code == 4
    assert data["ok"] is False
    assert data["resultado"] == "R"


def test_invoice_create_defaults_consumidor_final_condicion_iva(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 21)

    captured = {}

    class CapturingAdapter(FakeAFIPAdapter):
        def emit_factura_c(self, req):
            captured["condicion_iva_receptor_id"] = req.condicion_iva_receptor_id
            captured["fecha_serv_desde"] = req.fecha_serv_desde
            captured["fecha_serv_hasta"] = req.fecha_serv_hasta
            captured["fecha_venc_pago"] = req.fecha_venc_pago
            return super().emit_factura_c(req)

    monkeypatch.setattr(cli_mod.dt, "date", FixedDate)
    monkeypatch.setattr(cli_mod, "AFIPAdapter", CapturingAdapter)
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "99",
            "--doc-nro",
            "0",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            "20260320",
            "--concepto",
            "2",
        ],
        env=_base_env(tmp_path),
    )

    assert res.exit_code == 0
    assert captured["condicion_iva_receptor_id"] == 5
    assert captured["fecha_serv_desde"] == "20260320"
    assert captured["fecha_serv_hasta"] == "20260320"
    assert captured["fecha_venc_pago"] == "20260321"


def test_invoice_create_accepts_explicit_service_dates(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 21)

    captured = {}

    class CapturingAdapter(FakeAFIPAdapter):
        def emit_factura_c(self, req):
            captured["fecha_serv_desde"] = req.fecha_serv_desde
            captured["fecha_serv_hasta"] = req.fecha_serv_hasta
            captured["fecha_venc_pago"] = req.fecha_venc_pago
            return super().emit_factura_c(req)

    monkeypatch.setattr(cli_mod.dt, "date", FixedDate)
    monkeypatch.setattr(cli_mod, "AFIPAdapter", CapturingAdapter)
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "99",
            "--doc-nro",
            "0",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            "20260320",
            "--concepto",
            "2",
            "--fecha-serv-desde",
            "20260301",
            "--fecha-serv-hasta",
            "20260315",
        ],
        env=_base_env(tmp_path),
    )

    assert res.exit_code == 0
    assert captured["fecha_serv_desde"] == "20260301"
    assert captured["fecha_serv_hasta"] == "20260315"
    assert captured["fecha_venc_pago"] == "20260321"


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
    assert isinstance(data["errors"], list)


def test_invoice_create_rejects_invalid_cuit_without_persisting(tmp_path):
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
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["error_type"] == "validation"
    assert "CUIT inválido" in data["errors"]

    con = sqlite3.connect(tmp_path / "monofact.db")
    rows = con.execute("select count(*) from sqlite_master where type='table' and name='invoices'").fetchone()[0]
    assert rows == 0


def test_invoice_create_rejects_invalid_pto_vta_without_persisting(tmp_path):
    runner = CliRunner()
    env = _base_env(tmp_path)
    env["MONOFACT_PTO_VTA"] = "0"

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
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["error_type"] == "validation"
    assert "Punto de venta inválido" in data["errors"]

    con = sqlite3.connect(tmp_path / "monofact.db")
    rows = con.execute("select count(*) from sqlite_master where type='table' and name='invoices'").fetchone()[0]
    assert rows == 0


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


def test_invoice_last_rejects_invalid_runtime_settings(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    class FailingAdapter:
        def __init__(self, *args, **kwargs):
            raise AssertionError("AFIPAdapter no debería instanciarse")

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FailingAdapter)
    env = _base_env(tmp_path)
    env["MONOFACT_CUIT"] = "0"

    runner = CliRunner()
    res = runner.invoke(main, ["invoice-last"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["ok"] is False
    assert data["error_type"] == "validation"
    assert "CUIT inválido" in data["errors"]


def test_invoice_create_accepts_doc_tipo_alias(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    captured = {}

    class CapturingAdapter(FakeAFIPAdapter):
        def emit_factura_c(self, req):
            captured["doc_tipo"] = req.doc_tipo
            return super().emit_factura_c(req)

    monkeypatch.setattr(cli_mod, "AFIPAdapter", CapturingAdapter)
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "consumidor-final",
            "--doc-nro",
            "0",
            "--imp-total",
            "1500.00",
            "--cbte-fch",
            "20260320",
        ],
        env=_base_env(tmp_path),
    )

    assert res.exit_code == 0
    assert captured["doc_tipo"] == 99


def test_invoice_create_rejects_unknown_doc_tipo_alias(tmp_path):
    runner = CliRunner()
    res = runner.invoke(
        main,
        [
            "invoice-create",
            "--doc-tipo",
            "pasaporte",
            "--doc-nro",
            "12345678",
            "--imp-total",
            "1500.00",
        ],
        env=_base_env(tmp_path),
    )
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["error_type"] == "validation"
    assert "doc_tipo inválido" in data["errors"][0]


def test_invoice_list_by_cbte_nro(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)

    _create_invoice(runner, env, doc_tipo="dni")

    res = runner.invoke(main, ["invoice-list", "--cbte-nro", "124"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["count"] == 1
    assert data["items"][0]["cbte_nro"] == 124


def test_invoice_list_by_date_range(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)

    _create_invoice(runner, env, cbte_fch="20260301")

    res = runner.invoke(main, ["invoice-list", "--from", "20260301", "--to", "20260301"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["count"] == 1
    assert data["items"][0]["cbte_fch"] == "20260301"


def test_invoice_list_rejects_invalid_ranges(tmp_path):
    runner = CliRunner()
    res = runner.invoke(main, ["invoice-list", "--from", "20260302", "--to", "20260301"], env=_base_env(tmp_path))
    data = json.loads(res.output)

    assert res.exit_code == 2
    assert data["error_type"] == "validation"
    assert "--from no puede ser mayor que --to" in data["errors"]


def test_invoice_list_yaml_validation_error_preserves_exit_code(tmp_path):
    runner = CliRunner()
    res = runner.invoke(
        main,
        ["--format", "yaml", "invoice-list", "--from", "20260302", "--to", "20260301"],
        env=_base_env(tmp_path),
    )
    data = yaml.safe_load(res.output)

    assert res.exit_code == 2
    assert data["error_type"] == "validation"
    assert "--from no puede ser mayor que --to" in data["errors"]


def test_invoice_show_returns_afip_and_local(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)

    _create_invoice(runner, env)

    res = runner.invoke(main, ["invoice-show", "--cbte-nro", "124"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["source"] == "afip"
    assert data["local_fallback"] is False
    assert data["afip"]["cbte_nro"] == 124
    assert data["local"]["cbte_nro"] == 124


def test_invoice_show_falls_back_to_local(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)

    _create_invoice(runner, env)

    env["MONOFACT_TOKEN"] = "boom"
    res = runner.invoke(main, ["invoice-show", "--cbte-nro", "124"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 0
    assert data["source"] == "local"
    assert data["local_fallback"] is True
    assert data["local"]["cbte_nro"] == 124
    assert "fallo transporte" in data["afip_error"]


def test_invoice_show_not_found(monkeypatch, tmp_path):
    import monofact.cli as cli_mod

    monkeypatch.setattr(cli_mod, "AFIPAdapter", FakeAFIPAdapter)
    runner = CliRunner()
    env = _base_env(tmp_path)
    env["MONOFACT_TOKEN"] = "detail-fail"

    res = runner.invoke(main, ["invoice-show", "--cbte-nro", "999"], env=env)
    data = json.loads(res.output)

    assert res.exit_code == 4
    assert data["ok"] is False
    assert data["error_type"] == "not_found"
