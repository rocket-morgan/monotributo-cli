# Especificación V2 — MVP CLI Python (Factura C) **reutilizando PyAfipWs**

> Esta versión reemplaza el enfoque “cliente AFIP propio” por un enfoque de **reuso de repositorio existente**.
> Base analizada: `Projects/pyafipws` (commit `d595b07`).

---

## 1) Decisión arquitectónica (V2)

Para el caso de uso pedido (solo Factura C, sin PDF, guardando datos), la mejor estrategia es:

1. **Reutilizar PyAfipWs como motor AFIP** (WSAA + WSFEv1).
2. Construir un **wrapper CLI mínimo** con Click encima.
3. Persistir request/response/resultado en base local.

### ¿Por qué esta decisión?
- PyAfipWs ya implementa y mantiene la lógica SOAP de AFIP.
- Ya trae flujo probado para autenticación (WSAA) y autorización (WSFEv1/CAE).
- Reduce riesgo funcional y tiempo de salida.

---

## 2) Evidencia del análisis del repo clonado

Repositorio local:
- Ruta: `/data/workspace/Projects/pyafipws`
- Commit: `d595b07`

Hallazgos clave:
- Módulo `wsfev1.py`: interfaz completa para FEv1, incluyendo `CompUltimoAutorizado`, `CrearFactura`, `CAESolicitar`, `SetTicketAcceso`, etc.
- Módulo `wsaa.py`: autenticación con TRA/CMS para obtener token y sign.
- Ejemplo funcional `ejemplos/factura_electronica.py`: muestra flujo real WSAA → WSFEv1 → CAE.
- Config ejemplo `conf/rece.ini`: estructura de CUIT, punto de venta y endpoints homo/prod.

Conclusión técnica: **sí hay base sólida para evitar reinventar**.

---

## 3) Alcance del MVP V2

### Incluye
- CLI Python con Click.
- Emisión de **Factura C** (una por ejecución).
- Soporte `homo` y `prod`.
- Modo autenticación:
  - **MVP inicial:** token/sign manuales.
  - **Opcional en V2.1:** comando para renovar token vía WSAA.
- Persistencia local (SQLite recomendado).
- Salida JSON en stdout.

### No incluye
- PDF.
- Lotes.
- Notas de crédito/débito.
- Multi-CUIT/multi-tenant.

---

## 4) Diseño de integración (Wrapper sobre PyAfipWs)

## 4.1 Componentes

- `cli.py` (Click)
- `config.py` (archivo/env/flags)
- `afip_adapter.py` (adaptador a PyAfipWs)
- `invoice_service.py` (orquestación de emisión)
- `storage.py` (SQLite)

## 4.2 Adaptador AFIP (núcleo)

El adaptador debe encapsular llamadas a PyAfipWs para no acoplar toda la app a APIs internas del repo:

Funciones mínimas:
- `set_credentials(cuit, token, sign)`
- `connect_wsfe(env, cache_dir)`
- `get_last_cbte(tipo_cbte, pto_vta)`
- `create_factura_c(payload)`
- `solicitar_cae()`
- `parse_result()`

Con esto, si mañana cambia librería o versión, el impacto queda aislado.

---

## 5) CLI propuesta (V2)

Comando raíz: `monofact`

### 5.1 `monofact invoice:create`
Emite Factura C.

Flags mínimas:
- `--env [homo|prod]`
- `--cuit`
- `--pto-vta`
- `--doc-tipo`
- `--doc-nro`
- `--imp-total`
- `--cbte-fch YYYYMMDD` (default hoy)
- `--concepto` (default 2 servicios)
- `--token` / `--sign` (opcionales si vienen de config)
- `--force` (saltear guardia anti-duplicado)

Flags globales:
- `--format [json|yaml|yml]`
- `-v` / `--verbose` para humanizar códigos AFIP en la salida

### 5.2 `monofact invoice:last`
Consulta último comprobante autorizado (Factura C).

### 5.3 `monofact auth:check`
Valida que token/sign estén presentes y con formato plausible.

> Nota: comando `auth:refresh` (WSAA automático) se deja para V2.1 si querés mantener MVP ultra simple.

---

## 6) Mapeo de datos de negocio → PyAfipWs (Factura C)

Para Factura C (tipo comprobante AFIP correspondiente), el wrapper debe:

1. Consultar último número:
   - `CompUltimoAutorizado(tipo_cbte, pto_vta)`
2. Calcular `cbte_nro = ultimo + 1`
3. Llamar `CrearFactura(...)` con campos mínimos:
   - `concepto`
   - `tipo_doc`, `nro_doc`
   - `tipo_cbte` (Factura C)
   - `punto_vta`
   - `cbt_desde`, `cbt_hasta` (mismo número)
   - importes
   - `fecha_cbte`
   - `moneda_id=PES`, `moneda_ctz=1`
4. Llamar `CAESolicitar()`
5. Leer resultado (`CAE`, vencimiento, observaciones/errores)

---

## 7) Configuración

Archivo: `.monofact.toml`

```toml
[app]
default_env = "homo"
storage = "sqlite:///./monofact.db"
cache_dir = "./cache"

[afip]
cuit = "20123456789"
pto_vta = 1
tipo_comp_factura_c = 11

[auth]
token = ""
sign = ""

[endpoints.homo]
wsfe = "https://wswhomo.afip.gov.ar/wsfev1/service.asmx?WSDL"

[endpoints.prod]
wsfe = "https://servicios1.afip.gov.ar/wsfev1/service.asmx?WSDL"
```

Variables de entorno:
- `MONOFACT_ENV`, `MONOFACT_CUIT`, `MONOFACT_PTO_VTA`, `MONOFACT_TOKEN`, `MONOFACT_SIGN`

Precedencia:
1) flags CLI, 2) env vars, 3) archivo.

---

## 8) Persistencia (SQLite)

Tabla `invoices`:
- `id`, `created_at`, `env`, `cuit`, `pto_vta`, `tipo_comp`
- `cbte_nro`, `doc_tipo`, `doc_nro`, `cbte_fch`, `imp_total`
- `resultado`, `cae`, `cae_vto`
- `obs_json`, `errors_json`
- `request_json`, `response_json`
- `fingerprint`

Objetivo: auditoría y troubleshooting sin PDF.

---

## 9) Idempotencia mínima

Antes de emitir:
- Hash `fingerprint` con campos clave (cuit, pto_vta, doc, fecha, importe).
- Si existe emisión aprobada igual en ventana reciente, frenar y pedir `--force`.

---

## 10) Gestión de errores y salida

Formato error:
```json
{
  "ok": false,
  "error_type": "validation|transport|afip",
  "message": "...",
  "details": {}
}
```

Exit codes:
- `0` éxito
- `2` validación
- `3` transporte
- `4` rechazo AFIP
- `5` inesperado

---

## 11) Plan de implementación por fases

### Fase A (MVP puro, recomendado)
- Reusar PyAfipWs con token/sign manual.
- Implementar `invoice:create`, `invoice:last`, `auth:check`.
- Persistencia SQLite + logs.

### Fase B (V2.1 opcional)
- Agregar `auth:refresh` usando WSAA (cert/key).
- Cache de TA con expiración controlada.

### Fase C (V2.2)
- Lote simple (CSV/JSON)
- Notas de crédito C.

---

## 12) Comparativa rápida: V1 vs V2

- **V1:** orientado a diseñar CLI mínimo sin fijar integración concreta.
- **V2:** mismo MVP, pero **anclado en PyAfipWs** para bajar riesgo y tiempo.

Impacto esperado:
- Menos código propio crítico.
- Menos probabilidad de errores SOAP/AFIP.
- Time-to-first-invoice considerablemente menor.

---

## 13) Criterio de aceptación V2

Se considera exitoso cuando:
1. En homologación, `invoice:create` devuelve CAE para Factura C.
2. Guarda request/response/CAE en SQLite.
3. `invoice:last` informa último número correcto.
4. Errores se reportan en JSON con códigos de salida consistentes.

---

## 14) Recomendación final

Para tu objetivo, **no conviene reinventar**.
Conviene **usar PyAfipWs como motor** y hacer un CLI propio liviano para tu operación diaria.

Esa combinación te da velocidad ahora y control después.
