from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal

import click
import yaml

from .afip_adapter import AFIPAdapter, AFIPAdapterError, InvoiceInput, InvoiceNotFoundError
from .auth import (
    AuthError,
    AuthTransportError,
    inspect_auth,
    load_pyafipws_profile,
    resolve_auth_credentials,
)
from .config import load_settings
from .storage import (
    connect,
    get_invoice_by_cbte_nro,
    list_invoices_by_cbte_nro,
    list_invoices_by_date_range,
    save_invoice,
)


DOC_TIPO_ALIASES = {
    "dni": 96,
    "cuit": 80,
    "cuil": 86,
    "consumidor-final": 99,
    "consumidor_final": 99,
    "consumidorfinal": 99,
    "cf": 99,
}

CONCEPTO_LABELS = {
    1: "Productos",
    2: "Servicios",
    3: "Productos y Servicios",
}

TIPO_COMP_LABELS = {
    1: "Factura A",
    6: "Factura B",
    11: "Factura C",
}

DOC_TIPO_LABELS = {
    80: "CUIT",
    86: "CUIL",
    96: "DNI",
    99: "Consumidor Final",
}

RESULTADO_LABELS = {
    "A": "Aprobado",
    "R": "Rechazado",
    "P": "Pendiente",
}

ENV_LABELS = {
    "homo": "Homologación",
    "prod": "Producción",
}

MONEDA_LABELS = {
    "PES": "Pesos",
    "DOL": "Dólares",
}

COND_IVA_RECEPTOR_LABELS = {
    5: "Consumidor Final",
}

EMISION_TIPO_LABELS = {
    "CAE": "CAE",
    "CAEA": "CAEA",
}

VERBOSE_FIELD_MAPS = {
    "concepto": CONCEPTO_LABELS,
    "tipo_comp": TIPO_COMP_LABELS,
    "tipo_cbte": TIPO_COMP_LABELS,
    "doc_tipo": DOC_TIPO_LABELS,
    "tipo_doc": DOC_TIPO_LABELS,
    "resultado": RESULTADO_LABELS,
    "env": ENV_LABELS,
    "moneda_id": MONEDA_LABELS,
    "condicion_iva_receptor_id": COND_IVA_RECEPTOR_LABELS,
    "emision_tipo": EMISION_TIPO_LABELS,
}


def _normalize_output_format(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "yml":
        return "yaml"
    return normalized


def _get_output_format() -> str:
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return "json"
    root = ctx.find_root()
    if root.obj and "output_format" in root.obj:
        return root.obj["output_format"]
    return "json"


def _is_verbose_output() -> bool:
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return False
    root = ctx.find_root()
    if root.obj and "verbose" in root.obj:
        return bool(root.obj["verbose"])
    return False


def _humanize_value(field_name: str, value):
    labels = VERBOSE_FIELD_MAPS.get(field_name)
    if labels is None:
        return value
    return labels.get(value, value)


def _humanize_payload(value, *, field_name: str | None = None):
    if isinstance(value, dict):
        return {key: _humanize_payload(item, field_name=key) for key, item in value.items()}
    if isinstance(value, list):
        return [_humanize_payload(item, field_name=field_name) for item in value]
    if field_name is None:
        return value
    return _humanize_value(field_name, value)


def _serialize_payload(payload: dict) -> str:
    if _is_verbose_output():
        payload = _humanize_payload(payload)
    output_format = _get_output_format()
    if output_format == "yaml":
        return yaml.safe_dump(
            payload,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        ).rstrip()
    return json.dumps(payload, ensure_ascii=False)


def _print(payload: dict, code: int = 0):
    click.echo(_serialize_payload(payload))
    raise SystemExit(code)


def _validate_runtime_settings(settings) -> list[str]:
    errors = []
    if settings.cuit <= 0:
        errors.append("CUIT inválido")
    if settings.pto_vta <= 0:
        errors.append("Punto de venta inválido")
    try:
        inspect_auth(settings)
    except AuthError as exc:
        errors.append(str(exc))
    return errors


def _validate_local_lookup_settings(settings) -> list[str]:
    errors = []
    if settings.pto_vta <= 0:
        errors.append("Punto de venta inválido")
    if settings.tipo_comp_factura_c <= 0:
        errors.append("Tipo de comprobante inválido")
    return errors


def _normalize_alias(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _resolve_doc_tipo(value: str) -> int:
    raw = value.strip()
    if raw.isdigit():
        return int(raw)
    alias = _normalize_alias(raw)
    if alias in DOC_TIPO_ALIASES:
        return DOC_TIPO_ALIASES[alias]
    valid_values = ", ".join(sorted(set(DOC_TIPO_ALIASES)))
    raise click.BadParameter(f"doc_tipo inválido. Usá un código AFIP o uno de: {valid_values}")


def _validate_yyyymmdd(value: str, *, field_name: str) -> str:
    try:
        dt.datetime.strptime(value, "%Y%m%d")
    except ValueError as exc:
        raise click.BadParameter(f"{field_name} debe tener formato YYYYMMDD") from exc
    return value


def _build_list_filters(cbte_nro: int | None, date_from: str | None, date_to: str | None) -> tuple[str, dict]:
    if cbte_nro is not None and (date_from or date_to):
        raise click.BadParameter("Usá --cbte-nro o --from/--to, no ambos a la vez")
    if cbte_nro is None and not date_from and not date_to:
        raise click.BadParameter("Debés indicar --cbte-nro o bien --from y --to")
    if cbte_nro is not None:
        return "cbte_nro", {"cbte_nro": cbte_nro}
    if not date_from or not date_to:
        raise click.BadParameter("Para buscar por fechas tenés que indicar --from y --to")
    validated_from = _validate_yyyymmdd(date_from, field_name="from")
    validated_to = _validate_yyyymmdd(date_to, field_name="to")
    if validated_from > validated_to:
        raise click.BadParameter("--from no puede ser mayor que --to")
    return "date_range", {"from": validated_from, "to": validated_to}


def _build_afip_adapter(settings):
    creds = resolve_auth_credentials(settings)
    return AFIPAdapter(
        wsfe_url=settings.wsfe_url,
        cuit=settings.cuit,
        token=creds.token,
        sign=creds.sign,
        cache=settings.cache_dir,
    )


def _resolve_condicion_iva_receptor_id(doc_tipo: int, explicit_value: int | None) -> int | None:
    if explicit_value is not None:
        return explicit_value
    if doc_tipo == 99:
        return 5
    return None


def _resolve_service_dates(
    concepto: int,
    cbte_fch: str,
    fecha_serv_desde: str | None,
    fecha_serv_hasta: str | None,
) -> tuple[str | None, str | None, str | None]:
    if concepto in (2, 3):
        today = dt.date.today().strftime("%Y%m%d")
        return fecha_serv_desde or cbte_fch, fecha_serv_hasta or cbte_fch, today
    return None, None, None


@click.group()
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "yaml", "yml"], case_sensitive=False),
    default="json",
    show_default=True,
    help="Formato de salida del CLI.",
)
@click.option("-v", "--verbose", is_flag=True, help="Humaniza valores codificados en la salida.")
@click.pass_context
def main(ctx, output_format, verbose):
    """CLI MVP Factura C (Monotributo) sobre PyAfipWs."""
    ctx.ensure_object(dict)
    ctx.obj["output_format"] = _normalize_output_format(output_format)
    ctx.obj["verbose"] = verbose


@main.command("config-check")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--token")
@click.option("--sign")
def config_check(env, cuit, pto_vta, token, sign):
    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, token=token, sign=sign)
    errors = _validate_runtime_settings(s)

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
        creds = resolve_auth_credentials(s, force_refresh=force, allow_manual_credentials=False)
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
    except AuthTransportError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
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
    errors = _validate_runtime_settings(s)
    if errors:
        _print({"ok": False, "error_type": "validation", "errors": errors}, 2)
    try:
        afip = _build_afip_adapter(s)
        last = afip.get_last_cbte(s.tipo_comp_factura_c, s.pto_vta)
        _print({"ok": True, "last": last, "tipo_comp": s.tipo_comp_factura_c, "pto_vta": s.pto_vta})
    except AuthError as exc:
        _print({"ok": False, "error_type": "validation", "message": str(exc)}, 2)
    except AuthTransportError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except AFIPAdapterError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except Exception as exc:
        _print({"ok": False, "error_type": "unexpected", "message": str(exc)}, 5)


@main.command("invoice-create")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--tipo-comp", type=int)
@click.option("--doc-tipo", required=True)
@click.option("--doc-nro", type=int, required=True)
@click.option("--imp-total", type=Decimal, required=True)
@click.option("--cbte-fch", type=str)
@click.option(
    "--concepto",
    type=int,
    default=2,
    show_default=True,
    help="1=Productos, 2=Servicios, 3=Productos y Servicios.",
)
@click.option("--fecha-serv-desde", type=str)
@click.option("--fecha-serv-hasta", type=str)
@click.option("--cond-iva-receptor-id", type=int)
@click.option("--token")
@click.option("--sign")
def invoice_create(
    env,
    cuit,
    pto_vta,
    tipo_comp,
    doc_tipo,
    doc_nro,
    imp_total,
    cbte_fch,
    concepto,
    fecha_serv_desde,
    fecha_serv_hasta,
    cond_iva_receptor_id,
    token,
    sign,
):
    try:
        doc_tipo = _resolve_doc_tipo(doc_tipo)
    except click.BadParameter as exc:
        _print({"ok": False, "error_type": "validation", "errors": [exc.message]}, 2)

    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, tipo_comp=tipo_comp, token=token, sign=sign)
    resolved_cond_iva_receptor_id = _resolve_condicion_iva_receptor_id(doc_tipo, cond_iva_receptor_id)

    errors = _validate_runtime_settings(s)
    if imp_total <= 0:
        errors.append("imp_total debe ser > 0")
    if cbte_fch:
        try:
            _validate_yyyymmdd(cbte_fch, field_name="cbte_fch")
        except click.BadParameter as exc:
            errors.append(exc.message)
    if fecha_serv_desde:
        try:
            _validate_yyyymmdd(fecha_serv_desde, field_name="fecha_serv_desde")
        except click.BadParameter as exc:
            errors.append(exc.message)
    if fecha_serv_hasta:
        try:
            _validate_yyyymmdd(fecha_serv_hasta, field_name="fecha_serv_hasta")
        except click.BadParameter as exc:
            errors.append(exc.message)
    if errors:
        _print({"ok": False, "error_type": "validation", "errors": errors}, 2)

    if not cbte_fch:
        cbte_fch = dt.date.today().strftime("%Y%m%d")

    fecha_serv_desde, fecha_serv_hasta, fecha_venc_pago = _resolve_service_dates(
        concepto,
        cbte_fch,
        fecha_serv_desde,
        fecha_serv_hasta,
    )

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
        condicion_iva_receptor_id=resolved_cond_iva_receptor_id,
        fecha_serv_desde=fecha_serv_desde,
        fecha_serv_hasta=fecha_serv_hasta,
        fecha_venc_pago=fecha_venc_pago,
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
        "condicion_iva_receptor_id": resolved_cond_iva_receptor_id,
        "fecha_serv_desde": fecha_serv_desde,
        "fecha_serv_hasta": fecha_serv_hasta,
        "fecha_venc_pago": fecha_venc_pago,
    }

    try:
        afip = _build_afip_adapter(s)
        result = afip.emit_factura_c(req)
        conn = connect(s.db_path)
        rid = save_invoice(conn, payload, result)
        output = {**result, "record_id": rid}
        if _is_verbose_output():
            output.update(payload)
        _print(output, 0 if result.get("ok") else 4)
    except AuthError as exc:
        _print({"ok": False, "error_type": "validation", "message": str(exc)}, 2)
    except AuthTransportError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except AFIPAdapterError as exc:
        _print({"ok": False, "error_type": "transport", "message": str(exc)}, 3)
    except Exception as exc:
        _print({"ok": False, "error_type": "unexpected", "message": str(exc)}, 5)


@main.command("invoice-list")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--pto-vta", type=int)
@click.option("--tipo-comp", type=int)
@click.option("--cbte-nro", type=int)
@click.option("--from", "date_from", type=str)
@click.option("--to", "date_to", type=str)
def invoice_list(env, pto_vta, tipo_comp, cbte_nro, date_from, date_to):
    try:
        filter_kind, filters = _build_list_filters(cbte_nro, date_from, date_to)
    except click.BadParameter as exc:
        _print({"ok": False, "error_type": "validation", "errors": [exc.message]}, 2)

    s = load_settings(env=env, pto_vta=pto_vta, tipo_comp=tipo_comp)
    errors = _validate_local_lookup_settings(s)
    if errors:
        _print({"ok": False, "error_type": "validation", "errors": errors}, 2)

    conn = connect(s.db_path)
    if filter_kind == "cbte_nro":
        items = list_invoices_by_cbte_nro(
            conn,
            env=s.env,
            pto_vta=s.pto_vta,
            tipo_comp=s.tipo_comp_factura_c,
            cbte_nro=filters["cbte_nro"],
        )
    else:
        items = list_invoices_by_date_range(
            conn,
            env=s.env,
            pto_vta=s.pto_vta,
            tipo_comp=s.tipo_comp_factura_c,
            date_from=filters["from"],
            date_to=filters["to"],
        )

    _print({
        "ok": True,
        "count": len(items),
        "env": s.env,
        "pto_vta": s.pto_vta,
        "tipo_comp": s.tipo_comp_factura_c,
        "filters": filters,
        "items": items,
    })


@main.command("invoice-show")
@click.option("--env", type=click.Choice(["homo", "prod"]))
@click.option("--cuit", type=int)
@click.option("--pto-vta", type=int)
@click.option("--tipo-comp", type=int)
@click.option("--cbte-nro", type=int, required=True)
@click.option("--token")
@click.option("--sign")
def invoice_show(env, cuit, pto_vta, tipo_comp, cbte_nro, token, sign):
    s = load_settings(env=env, cuit=cuit, pto_vta=pto_vta, tipo_comp=tipo_comp, token=token, sign=sign)
    errors = _validate_local_lookup_settings(s)
    if cbte_nro <= 0:
        errors.append("cbte_nro debe ser > 0")
    if errors:
        _print({"ok": False, "error_type": "validation", "errors": errors}, 2)

    conn = connect(s.db_path)
    local_detail = get_invoice_by_cbte_nro(
        conn,
        env=s.env,
        pto_vta=s.pto_vta,
        tipo_comp=s.tipo_comp_factura_c,
        cbte_nro=cbte_nro,
    )

    afip_detail = None
    afip_error = None
    afip_exc = None
    try:
        afip = _build_afip_adapter(s)
        afip_detail = afip.get_invoice_detail(s.tipo_comp_factura_c, s.pto_vta, cbte_nro)
    except (AuthError, AuthTransportError, AFIPAdapterError, Exception) as exc:
        afip_exc = exc
        afip_error = str(exc)

    if afip_detail is not None:
        payload = {
            "ok": True,
            "source": "afip",
            "local_fallback": False,
            "env": s.env,
            "pto_vta": s.pto_vta,
            "tipo_comp": s.tipo_comp_factura_c,
            "cbte_nro": cbte_nro,
            "afip": afip_detail,
        }
        if local_detail is not None:
            payload["local"] = local_detail
        _print(payload)

    if local_detail is not None:
        _print({
            "ok": True,
            "source": "local",
            "local_fallback": True,
            "env": s.env,
            "pto_vta": s.pto_vta,
            "tipo_comp": s.tipo_comp_factura_c,
            "cbte_nro": cbte_nro,
            "afip": None,
            "afip_error": afip_error,
            "local": local_detail,
        })

    if isinstance(afip_exc, AuthError):
        _print({"ok": False, "error_type": "validation", "message": afip_error}, 2)
    if isinstance(afip_exc, (AuthTransportError, AFIPAdapterError)) and not isinstance(afip_exc, InvoiceNotFoundError):
        _print({"ok": False, "error_type": "transport", "message": afip_error}, 3)
    if afip_exc is not None and not isinstance(afip_exc, InvoiceNotFoundError):
        _print({"ok": False, "error_type": "unexpected", "message": afip_error}, 5)

    _print({
        "ok": False,
        "error_type": "not_found",
        "message": "Factura no encontrada en AFIP ni en la base local.",
        "env": s.env,
        "pto_vta": s.pto_vta,
        "tipo_comp": s.tipo_comp_factura_c,
        "cbte_nro": cbte_nro,
        "afip_error": afip_error,
    }, 4)


if __name__ == "__main__":
    main()
