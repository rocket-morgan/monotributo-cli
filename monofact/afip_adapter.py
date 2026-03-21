from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256


@dataclass
class InvoiceInput:
    env: str
    cuit: int
    pto_vta: int
    tipo_comp: int
    doc_tipo: int
    doc_nro: int
    imp_total: Decimal
    cbte_fch: str
    concepto: int
    condicion_iva_receptor_id: int | None = None
    fecha_serv_desde: str | None = None
    fecha_serv_hasta: str | None = None
    fecha_venc_pago: str | None = None


class AFIPAdapterError(Exception):
    pass


class AFIPAdapter:
    def __init__(self, wsfe_url: str, cuit: int, token: str, sign: str, cache: str = "./cache"):
        self.wsfe_url = wsfe_url
        self.cuit = cuit
        self.token = token
        self.sign = sign
        self.cache = cache
        self._ws = None

    def _get_ws(self):
        if self._ws is not None:
            return self._ws
        try:
            from pyafipws.wsfev1 import WSFEv1
        except Exception as exc:
            raise AFIPAdapterError("No se pudo importar pyafipws. Instalá pyafipws en el entorno.") from exc

        ws = WSFEv1()
        ws.Cuit = self.cuit
        ws.Token = self.token
        ws.Sign = self.sign
        ws.Conectar(self.cache, self.wsfe_url)
        self._ws = ws
        return ws

    def get_last_cbte(self, tipo_comp: int, pto_vta: int) -> int:
        ws = self._get_ws()
        last = ws.CompUltimoAutorizado(tipo_comp, pto_vta)
        return int(last)

    def get_invoice_detail(self, tipo_comp: int, pto_vta: int, cbte_nro: int) -> dict:
        ws = self._get_ws()
        ws.CompConsultar(tipo_comp, pto_vta, cbte_nro)
        factura = getattr(ws, "factura", None) or {}
        if not factura:
            errors = getattr(ws, "Errores", None) or []
            message = "No se pudo consultar el comprobante en AFIP."
            if errors:
                message = " / ".join(str(err) for err in errors)
            raise AFIPAdapterError(message)

        return {
            "tipo_comp": int(factura.get("tipo_cbte") or tipo_comp),
            "pto_vta": int(factura.get("punto_vta") or pto_vta),
            "cbte_nro": int(factura.get("cbt_hasta") or cbte_nro),
            "resultado": factura.get("resultado") or getattr(ws, "Resultado", ""),
            "cae": factura.get("cae") or getattr(ws, "CAE", ""),
            "cae_vto": factura.get("fch_venc_cae") or getattr(ws, "Vencimiento", ""),
            "emision_tipo": getattr(ws, "EmisionTipo", ""),
            "obs": factura.get("obs", []),
            "errors": getattr(ws, "Errores", None) or [],
            "invoice": factura,
        }

    def emit_factura_c(self, data: InvoiceInput) -> dict:
        ws = self._get_ws()
        last = self.get_last_cbte(data.tipo_comp, data.pto_vta)
        next_cbte = last + 1

        ws.CrearFactura(
            concepto=data.concepto,
            tipo_doc=data.doc_tipo,
            nro_doc=data.doc_nro,
            tipo_cbte=data.tipo_comp,
            punto_vta=data.pto_vta,
            cbt_desde=next_cbte,
            cbt_hasta=next_cbte,
            imp_total=float(data.imp_total),
            imp_tot_conc=0.00,
            imp_neto=float(data.imp_total),
            imp_iva=0.00,
            imp_trib=0.00,
            imp_op_ex=0.00,
            fecha_cbte=data.cbte_fch,
            fecha_serv_desde=data.fecha_serv_desde,
            fecha_serv_hasta=data.fecha_serv_hasta,
            fecha_venc_pago=data.fecha_venc_pago,
            moneda_id="PES",
            moneda_ctz="1.0000",
            condicion_iva_receptor_id=data.condicion_iva_receptor_id,
        )
        ws.CAESolicitar()

        fp = sha256(
            f"{data.cuit}|{data.pto_vta}|{data.doc_tipo}|{data.doc_nro}|{data.cbte_fch}|{data.imp_total}".encode()
        ).hexdigest()

        return {
            "ok": ws.Resultado == "A",
            "resultado": ws.Resultado,
            "cbte_nro": next_cbte,
            "cae": ws.CAE,
            "cae_vto": ws.Vencimiento,
            "obs": getattr(ws, "Observaciones", None) or [],
            "errors": getattr(ws, "Errores", None) or [],
            "fingerprint": fp,
        }
