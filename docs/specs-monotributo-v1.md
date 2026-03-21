# Especificación MVP — CLI Python para emitir Factura C (Monotributo) en AFIP/ARCA

## 1) Objetivo
Definir un **MVP funcional y mínimo** para emitir **Factura C** desde línea de comandos, usando Python.

Alcance del MVP:
- Emitir **1 comprobante por ejecución**.
- Tipo de comprobante: **Factura C**.
- Sin generación de PDF.
- Persistencia local de datos de emisión (request/response + CAE).
- Operación en homologación y producción.

No incluye (en esta fase):
- UI web.
- Multiusuario/multicuenta.
- Notas de crédito/débito.
- Lotes masivos.
- Reintentos avanzados/colas.

---

## 2) Enfoque técnico
Se usará Python con:
- **Click** para CLI.
- Cliente SOAP (vía librería AFIP existente o integración SOAP directa).
- Persistencia local en SQLite o JSONL (SQLite recomendado).

### Decisión MVP sobre autenticación
Para simplificar y acelerar:
- El MVP operará con **Token + Sign ya obtenidos** (cargados por config/CLI).
- No implementa inicialmente la obtención automática de token (WSAA).

Esto permite validar rápido el flujo central: **solicitar CAE para Factura C**.

> Fase siguiente (fuera de este documento): agregar comando `auth` para renovar token automáticamente.

---

## 3) Requisitos funcionales

### RF-01 Emitir Factura C
El sistema debe permitir emitir una Factura C y devolver:
- Resultado (aprobado/rechazado)
- CAE (si aplica)
- Vencimiento de CAE
- Número de comprobante
- Mensajes/observaciones de AFIP

### RF-02 Obtener último número
Antes de emitir, debe consultar el último comprobante para:
- Calcular el siguiente número secuencial
- Evitar inconsistencias de numeración

### RF-03 Persistir trazabilidad
Guardar localmente:
- Payload enviado
- Respuesta completa
- Metadatos (fecha, ambiente, CUIT, pto_vta, tipo_comp)

### RF-04 Validación mínima de entrada
Validar antes de enviar:
- CUIT emisor
- Punto de venta
- Tipo doc receptor + número
- Importe total > 0
- Fecha de comprobante válida

### RF-05 Modo homologación/producción
Permitir cambiar entorno por config y/o flag CLI.

---

## 4) Requisitos no funcionales
- **Simplicidad primero**: código corto y mantenible.
- **Idempotencia básica**: evitar doble emisión accidental por error humano.
- **Observabilidad mínima**: logs claros de request/response y errores AFIP.
- **Seguridad básica**: no loguear secretos completos (token/sign completos ocultos en logs).

---

## 5) Diseño de CLI (Click)

Comando raíz sugerido: `monofact`

### 5.1 Comandos MVP

#### `monofact invoice:create`
Emite una Factura C.

Parámetros sugeridos:
- `--env [homo|prod]`
- `--cuit <int>`
- `--pto-vta <int>`
- `--doc-tipo <int>` (ej. DNI/CUIT según tabla AFIP)
- `--doc-nro <int>`
- `--imp-total <decimal>`
- `--concepto <int>` (productos/servicios/ambos)
- `--cbte-fch <YYYYMMDD>` (default: hoy)
- `--token <str>` (opcional, si no viene de config)
- `--sign <str>` (opcional, si no viene de config)
- `--format [json|yaml|yml]` (default: `json`)

Salida:
- `json` en stdout para scripting
- `yaml`/`yml` en stdout con el mismo payload, pero en formato más legible para humanos

#### `monofact invoice:last`
Consulta último comprobante autorizado.

Parámetros:
- `--env`
- `--cuit`
- `--pto-vta`
- `--tipo-comp` (para MVP fijar Factura C, pero mantener parámetro)
- `--token`
- `--sign`

#### `monofact config:check`
Valida configuración activa:
- Variables requeridas
- Conectividad mínima
- Formato de credenciales

---

## 6) Configuración

Archivo sugerido: `.monofact.toml`

Ejemplo:
```toml
[app]
default_env = "homo"
storage = "sqlite:///./monofact.db"

[afip]
cuit = "20123456789"
pto_vta = 1
tipo_comp_factura_c = 11

[auth]
# MVP: token/sign manuales
# Pueden venir de env vars o CLI y sobrescribir estos valores
token = ""
sign = ""

[endpoints.homo]
wsfe = "..."

[endpoints.prod]
wsfe = "..."
```

Variables de entorno equivalentes:
- `MONOFACT_ENV`
- `MONOFACT_CUIT`
- `MONOFACT_PTO_VTA`
- `MONOFACT_TOKEN`
- `MONOFACT_SIGN`

Precedencia recomendada:
1. Flags CLI
2. Env vars
3. Archivo config

---

## 7) Modelo de datos (persistencia)

Tabla/estructura `invoices`:
- `id` (uuid)
- `created_at` (timestamp)
- `env` (homo/prod)
- `cuit`
- `pto_vta`
- `tipo_comp` (Factura C)
- `cbte_nro`
- `doc_tipo`
- `doc_nro`
- `cbte_fch`
- `imp_total`
- `resultado` (A/R/P)
- `cae` (nullable)
- `cae_vto` (nullable)
- `obs_json`
- `errors_json`
- `request_json`
- `response_json`
- `fingerprint` (hash para idempotencia básica)

Tabla/estructura `runs` (opcional simple):
- `id`
- `command`
- `status`
- `started_at`
- `finished_at`
- `error_message`

---

## 8) Flujo funcional de emisión

1. Cargar config (CLI/env/archivo)
2. Validar input
3. Construir cliente WSFE
4. Consultar último número
5. Calcular próximo número
6. Armar request FECAESolicitar (Factura C)
7. Enviar solicitud
8. Procesar respuesta
9. Persistir request/response
10. Imprimir JSON final en stdout

---

## 9) Idempotencia mínima (anti doble emisión)

Antes de emitir:
- Generar `fingerprint` con campos clave:
  - cuit + pto_vta + doc_tipo + doc_nro + imp_total + cbte_fch
- Si existe comprobante exitoso reciente con el mismo fingerprint:
  - Devolver aviso y requerir `--force` para reintentar.

Esto reduce errores operativos sin complejizar demasiado.

---

## 10) Manejo de errores (MVP)

Categorías:
1. **Validación local** (input inválido)
2. **Conectividad/transporte** (timeout, DNS, SSL)
3. **Negocio AFIP** (rechazos, observaciones, códigos)

Formato de salida de error (JSON):
```json
{
  "ok": false,
  "error_type": "validation|transport|afip",
  "message": "...",
  "details": {}
}
```

Exit codes sugeridos:
- `0`: éxito
- `2`: validación local
- `3`: conectividad/transporte
- `4`: rechazo AFIP
- `5`: error inesperado

---

## 11) Estructura de proyecto sugerida

```text
monofact/
  pyproject.toml
  README.md
  .env.example
  monofact/
    __init__.py
    cli.py
    config.py
    models.py
    storage.py
    afip_client.py
    services/
      invoice_service.py
    utils/
      validators.py
      logging.py
  tests/
    test_validators.py
    test_cli_smoke.py
```

---

## 12) Contrato de salida del comando principal

Respuesta exitosa ejemplo:
```json
{
  "ok": true,
  "env": "homo",
  "cuit": "20123456789",
  "pto_vta": 1,
  "tipo_comp": 11,
  "cbte_nro": 123,
  "resultado": "A",
  "cae": "12345678901234",
  "cae_vto": "20260331",
  "obs": [],
  "errors": []
}
```

Respuesta rechazada ejemplo:
```json
{
  "ok": false,
  "error_type": "afip",
  "resultado": "R",
  "errors": [
    {"code": 10000, "msg": "..."}
  ],
  "obs": []
}
```

---

## 13) Plan de pruebas MVP

Casos mínimos:
1. Config válida + credenciales válidas + emisión OK
2. Falta token/sign
3. Importe inválido
4. Error de conectividad
5. Rechazo AFIP por datos inválidos
6. Reintento duplicado sin `--force`

Criterio de aceptación MVP:
- Se puede emitir una Factura C desde CLI y recuperar CAE.
- Queda persistida la trazabilidad local completa.
- Los errores salen claros y con código de salida consistente.

---

## 14) Riesgos y mitigaciones
- **Token expirado** → mensaje claro y comando recomendado para renovar (futuro `auth`).
- **Diferencias homo/prod** → config por entorno bien separada.
- **Duplicación humana** → fingerprint + `--force`.
- **Datos fiscales mal cargados** → validaciones previas + errores explícitos.

---

## 15) Roadmap inmediato (post-MVP)
1. Comando `auth:refresh` (WSAA automático)
2. Soporte Nota de Crédito C
3. Export CSV/JSON de emisiones
4. Modo batch
5. Integración como librería reutilizable

---

## 16) Resumen ejecutivo
Este MVP propone un CLI en Python, con Click, centrado únicamente en **emitir Factura C** y guardar trazabilidad. Para reducir complejidad inicial, usa token/sign manuales. Con eso ya cubre el caso esencial: **generar comprobante electrónico y obtener CAE** de forma operativa, auditable y simple.
