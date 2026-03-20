from decimal import Decimal

from monofact.afip_adapter import AFIPAdapter, InvoiceInput


class FakeWS:
    def __init__(self, last=41, resultado="A", cae="12345678901234", vto="20260331"):
        self._last = last
        self.Resultado = resultado
        self.CAE = cae
        self.Vencimiento = vto
        self.Observaciones = []
        self.Errores = []
        self.crear_factura_calls = []
        self.solicitar_calls = 0

    def CompUltimoAutorizado(self, tipo_comp, pto_vta):
        return self._last

    def CrearFactura(self, **kwargs):
        self.crear_factura_calls.append(kwargs)

    def CAESolicitar(self):
        self.solicitar_calls += 1


def test_emit_factura_c_ok(monkeypatch):
    fake_ws = FakeWS(last=100, resultado="A")
    adapter = AFIPAdapter("http://fake/wsdl", cuit=20123456789, token="tok", sign="sig")
    monkeypatch.setattr(adapter, "_get_ws", lambda: fake_ws)

    req = InvoiceInput(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        tipo_comp=11,
        doc_tipo=96,
        doc_nro=12345678,
        imp_total=Decimal("1000.00"),
        cbte_fch="20260301",
        concepto=1,
    )

    res = adapter.emit_factura_c(req)

    assert res["ok"] is True
    assert res["resultado"] == "A"
    assert res["cbte_nro"] == 101
    assert res["cae"] == "12345678901234"
    assert len(res["fingerprint"]) == 64
    assert fake_ws.solicitar_calls == 1
    assert fake_ws.crear_factura_calls[0]["tipo_cbte"] == 11
    assert fake_ws.crear_factura_calls[0]["condicion_iva_receptor_id"] is None


def test_emit_factura_c_rejected(monkeypatch):
    fake_ws = FakeWS(last=5, resultado="R", cae="", vto="")
    fake_ws.Errores = ["10000: rechazo de prueba"]
    adapter = AFIPAdapter("http://fake/wsdl", cuit=20123456789, token="tok", sign="sig")
    monkeypatch.setattr(adapter, "_get_ws", lambda: fake_ws)

    req = InvoiceInput(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        tipo_comp=11,
        doc_tipo=96,
        doc_nro=12345678,
        imp_total=Decimal("1.00"),
        cbte_fch="20260301",
        concepto=1,
    )

    res = adapter.emit_factura_c(req)

    assert res["ok"] is False
    assert res["resultado"] == "R"
    assert res["errors"] == ["10000: rechazo de prueba"]


def test_get_last_cbte(monkeypatch):
    fake_ws = FakeWS(last=77)
    adapter = AFIPAdapter("http://fake/wsdl", cuit=20123456789, token="tok", sign="sig")
    monkeypatch.setattr(adapter, "_get_ws", lambda: fake_ws)

    assert adapter.get_last_cbte(11, 1) == 77


def test_emit_factura_c_passes_condicion_iva_receptor_id(monkeypatch):
    fake_ws = FakeWS(last=10, resultado="A")
    adapter = AFIPAdapter("http://fake/wsdl", cuit=20123456789, token="tok", sign="sig")
    monkeypatch.setattr(adapter, "_get_ws", lambda: fake_ws)

    req = InvoiceInput(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        tipo_comp=11,
        doc_tipo=99,
        doc_nro=0,
        imp_total=Decimal("1000.00"),
        cbte_fch="20260320",
        concepto=2,
        condicion_iva_receptor_id=5,
    )

    adapter.emit_factura_c(req)

    assert fake_ws.crear_factura_calls[0]["condicion_iva_receptor_id"] == 5


def test_emit_factura_c_passes_service_dates(monkeypatch):
    fake_ws = FakeWS(last=10, resultado="A")
    adapter = AFIPAdapter("http://fake/wsdl", cuit=20123456789, token="tok", sign="sig")
    monkeypatch.setattr(adapter, "_get_ws", lambda: fake_ws)

    req = InvoiceInput(
        env="homo",
        cuit=20123456789,
        pto_vta=1,
        tipo_comp=11,
        doc_tipo=99,
        doc_nro=0,
        imp_total=Decimal("1000.00"),
        cbte_fch="20260320",
        concepto=2,
        fecha_serv_desde="20260320",
        fecha_serv_hasta="20260320",
        fecha_venc_pago="20260320",
    )

    adapter.emit_factura_c(req)

    assert fake_ws.crear_factura_calls[0]["fecha_serv_desde"] == "20260320"
    assert fake_ws.crear_factura_calls[0]["fecha_serv_hasta"] == "20260320"
    assert fake_ws.crear_factura_calls[0]["fecha_venc_pago"] == "20260320"
