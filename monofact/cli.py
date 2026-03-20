from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import click

from .afip_adapter import AFIPAdapter, AFIPAdapterError, InvoiceInput
from .auth import AuthError, inspect_auth, load_pyafipws_profile, resolve_auth_credentials
from .config import load_settings
from .storage import connect, save_invoice


def _print(payload: dict, code: int = 0):
    click.echo(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(code)


@click.group()
def main():
    """CLI MVP Factura C (Monotributo) sobre PyAfipWs."""


@main.command("config-check")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--token")
@click.option("--sign")
def config_check(env, cuit, pto_vta, token, sign):
    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, token=token, sign=sign)
    errors = []
    if s.cuit <= 0:
        errors.append("CUIT inválido")
    if s.pto_vta <= 0:
        errors.append("Punto de venta inválido")
    try:
        inspect_auth(s)
    except AuthError as exc:
        errors.append(str(exc))

    if errors:
        _print({"ok": False, "error_type": "validation", "errors": errors}, 2)

    _print({
        "ok": True,
        "env": s.env,
        "cuit": s.cuit,
        "pto_vta": s.pto_vta,
        "wsfe_url": s.wsfe_url,
    })


@main.command("auth-refresh")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--force/--no-force", default=False)
def auth_refresh(env, force):
    s = load_settings(env=env)
    try:
        profile = load_pyafipws_profile(s)
        creds = resolve_auth_credentials(s, force_refresh=force)
        _print({
            "ok": True,
            "env": s.env,
            "profile": profile.profile_name,
            "pyafipws_dir": s.pyafipws_dir,
            "ta_path": str(creds.ta_path) if creds.ta_path else None,
            "expires_at": creds.expiration_time,
            "forced": force,
        })
    except AuthError as exc:
        _print({"ok": False, "error_type": "validation", "message": str(exc)}, 2)
    except AFIPAdapterError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except Exception as exc:
        _print({"ok": False, "error_type": "unexpected", "message": str(exc)}, 5)


@main.command("invoice-last")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--tipo-comp", type=int)
@click.option("--token")
@click.option("--sign")
def invoice_last(env, cuit, pto_vta, tipo_comp, token, sign):
    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, tipo_comp=tipo_comp, token=token, sign=sign)
    try:
        creds = resolve_auth_credentials(s)
        afip = AFIPAdapter(wsfe_url=s.wsfe_url, cuit=s.cuit, token=creds.token, sign=creds.sign)
        last = afip.get_last_cbte(s.tipo_comp_factura_c, s.pto_vta)
        _print({"ok": True, "last": last, "tipo_comp": s.tipo_comp_factura_c, "pto_vta": s.pto_vta})
    except AuthError as exc:
        _print({"ok": False, "error_type": "validation", "message": str(exc)}, 2)
    except AFIPAdapterError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except Exception as exc:
        _print({"ok": False, "error_type": "unexpected", "message": str(exc)}, 5)


@main.command("invoice-create")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--tipo-comp", type=int)
@click.option("--doc-tipo", type=int, required=True)
@click.option("--doc-nro", type=int, required=True)
@click.option("--imp-total", type=Decimal, required=True)
@click.option("--cbte-fch", type=str)
@click.option("--concepto", type=int, default=1)
@click.option("--token")
@click.option("--sign")
def invoice_create(env, cuit, pto_vta, tipo_comp, doc_tipo, doc_nro, imp_total, cbte_fch, concepto, token, sign):
    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, tipo_comp=tipo_comp, token=token, sign=sign)

    if imp_total <= 0:
        _print({"ok": False, "error_type": "validation", "message": "imp_total debe ser > 0"}, 2)

    if not cbte_fch:
        cbte_fch = dt.date.today().strftime("%Y%m%d")

    req = InvoiceInput(
        env=s.env,
        cuit=s.cuit,
        pto_vta=s.pto_vta,
        tipo_comp=s.tipo_comp_factura_c,
        doc_tipo=doc_tipo,
        doc_nro=doc_nro,
        imp_total=imp_total,
        cbte_fch=cbte_fch,
        concepto=concepto,
    )

    payload = {
        "env": s.env,
        "cuit": s.cuit,
        "pto_vta": s.pto_vta,
        "tipo_comp": s.tipo_comp_factura_c,
        "doc_tipo": doc_tipo,
        "doc_nro": doc_nro,
        "imp_total": str(imp_total),
        "cbte_fch": cbte_fch,
        "concepto": concepto,
    }

    try:
        creds = resolve_auth_credentials(s)
        afip = AFIPAdapter(wsfe_url=s.wsfe_url, cuit=s.cuit, token=creds.token, sign=creds.sign)
        result = afip.emit_factura_c(req)
        conn = connect(s.db_path)
        rid = save_invoice(conn, payload, result)
        result["record_id"] = rid
        _print(result, 0 if result.get("ok") else 4)
    except AuthError as exc:
        _print({"ok": False, "error_type": "validation", "message": str(exc)}, 2)
    except AFIPAdapterError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except Exception as exc:
        _print({"ok": False, "error_type": "unexpected", "message": str(exc)}, 5)


if __name__ == "__main__":
    main()
