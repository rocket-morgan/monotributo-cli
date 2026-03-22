# AGENTS.md

## Resumen rápido

`monotributo-cli` es un CLI Python para emitir Factura C de Monotributo usando `pyafipws` como librería embebida, no como servicio externo.

Comandos principales:

- `monofact config-check`
- `monofact auth-refresh`
- `monofact invoice-last`
- `monofact invoice-create`
- `monofact invoice-list`
- `monofact invoice-show`

Flags globales útiles:

- `--format [json|yaml|yml]`
- `-v` / `--verbose` para humanizar códigos AFIP en la salida

El entrypoint del CLI está en `monofact/cli.py`.

## Estructura del repo

- `monofact/cli.py`: comandos Click, validaciones, códigos de salida, salida JSON.
- `monofact/config.py`: carga de configuración desde flags y variables de entorno.
- `monofact/afip_adapter.py`: wrapper sobre `pyafipws.wsfev1.WSFEv1`.
- `monofact/storage.py`: persistencia SQLite y queries locales de listado/detalle.
- `tests/test_cli_contract.py`: contrato de payloads JSON del CLI.
- `tests/test_cli_integration.py`: tests de integración del CLI usando fake adapter.
- `tests/test_afip_adapter.py`: tests unitarios del adapter con fake WS.
- `scripts/smoke_homo.sh`: smoke test real de homologación.
- `docs/specs-monotributo-v1.md` y `docs/specs-monotributo-v2.md`: specs del proyecto.

## Dependencias y entorno

El proyecto usa `uv`.

Setup actual:

- Python pinneado en `.python-version`: `3.14.3`
- lockfile: `uv.lock`
- `pyafipws` se instala desde el checkout local `../pyafipws`
- `pyafipws` está configurado como dependencia editable en `pyproject.toml`
- `.env` se auto-carga si existe en el cwd
- si faltan `token/sign`, el CLI intenta resolverlos desde `pyafipws`

Comando de bootstrap:

```bash
uv sync --dev
```

## Importante sobre Python 3.14

`pyafipws` importa `pysimplesoap`, y esa librería todavía usa `distutils`. En Python 3.14 `distutils` ya no viene en stdlib, así que el entorno necesita `setuptools` instalado para exponer el shim compatible.

Por eso `setuptools>=82` quedó declarado como dependencia del proyecto en `pyproject.toml`.

Síntoma si esto se rompe:

```python
ModuleNotFoundError: No module named 'distutils'
```

Smoke test de import:

```bash
uv run python -c "from pyafipws.wsfev1 import WSFEv1; print('WSFEv1 import ok')"
```

## Cómo funciona

Resolución de credenciales:

1. Si `MONOFACT_TOKEN` y `MONOFACT_SIGN` están presentes, se usan tal cual.
2. Si ambos parecen referencias a archivos locales en vez de credenciales reales, se ignoran y se usa `pyafipws`.
3. Si faltan, el CLI busca `pyafipws` en `MONOFACT_PYAFIPWS_DIR`.
4. Según `env`, usa:
   - `homo` -> `conf/homologacion.ini`
   - `prod` -> `conf/produccion.ini`
5. Llama `WSAA.Autenticar(...)`.
6. Reutiliza el TA cacheado en `pyafipws/cache/TA-*.xml` y lo renueva si hace falta.

Flujo de `invoice-last`:

1. `cli.py` carga settings desde flags/env.
2. Resuelve `token/sign` manualmente o vía `pyafipws`.
3. Instancia `AFIPAdapter`.
4. `AFIPAdapter` importa `WSFEv1`, conecta al WSDL y consulta el último comprobante.
5. El CLI devuelve JSON a stdout.

Flujo de `invoice-create`:

1. `cli.py` valida `imp_total` y completa `cbte_fch` si falta.
2. Construye `InvoiceInput`.
3. Resuelve `token/sign` manualmente o vía `pyafipws`.
4. `AFIPAdapter.emit_factura_c()` consulta último comprobante, calcula el siguiente y llama `CrearFactura()` + `CAESolicitar()`.
5. `storage.py` persiste request y response en SQLite.
6. El CLI devuelve JSON con `record_id`; con `-v` agrega además metadatos del request humanizados.

Flujo de `invoice-list`:

1. `cli.py` valida que venga `--cbte-nro` o bien `--from` + `--to`.
2. Carga settings desde flags/env para resolver `env`, `pto_vta` y `tipo_comp`.
3. `storage.py` consulta SQLite local.
4. El CLI devuelve JSON resumido con `count` e `items`.

Flujo de `invoice-show`:

1. `cli.py` resuelve `env`, `pto_vta` y `tipo_comp`.
2. Busca primero el comprobante en SQLite local.
3. Intenta consultar AFIP con `AFIPAdapter.get_invoice_detail()` usando `CompConsultar`.
4. Si AFIP responde, devuelve `source = "afip"` y agrega `local` si existe registro persistido.
5. Si AFIP falla pero existe registro local, devuelve `source = "local"` con `local_fallback = true`.

Defaults relevantes al emitir:

- `--concepto` default: `2` (Servicios)
- si `doc_tipo == 99`, el CLI completa `condicion_iva_receptor_id = 5` (Consumidor Final)
- si `concepto in (2, 3)`, completa `fecha_serv_desde` y `fecha_serv_hasta` con `cbte_fch` salvo que se pasen por parámetro
- si `concepto in (2, 3)`, completa `fecha_venc_pago` con la fecha actual de ejecución del comando
- `--doc-tipo` acepta aliases locales:
  - `dni` -> `96`
  - `cuit` -> `80`
  - `cuil` -> `86`
  - `consumidor-final` y `cf` -> `99`

Persistencia:

- DB por default: `./monofact.db`
- tabla: `invoices`
- guarda request, response, CAE, observaciones, errores y fingerprint.

## Variables de entorno

Las variables soportadas hoy son:

- `MONOFACT_ENV`
- `MONOFACT_CUIT`
- `MONOFACT_PTO_VTA`
- `MONOFACT_TIPO_COMP_FACTURA_C`
- `MONOFACT_TOKEN`
- `MONOFACT_SIGN`
- `MONOFACT_DB_PATH`
- `MONOFACT_PYAFIPWS_DIR`
- `MONOFACT_WSFE_HOMO`
- `MONOFACT_WSFE_PROD`

Template base: `.env.example`

Precedencia:

1. flags CLI
2. variables exportadas en shell
3. `.env`
4. defaults

## Qué requiere `pyafipws`

Punto clave:

- `config-check` no necesita importar `pyafipws`
- `auth-refresh`, `invoice-last` e `invoice-create` usan `pyafipws` si faltan `token/sign`
- `invoice-last` e `invoice-create` validan `cuit` y `pto_vta` antes de llamar a AFIP

El CLI no levanta `pyafipws` como proceso aparte y no consume Docker ni HTTP intermedio. Todo corre dentro del mismo proceso Python.

## Cómo testear

Suite completa:

```bash
uv run pytest -q
```

Estado conocido al momento de escribir este archivo:

- `41 passed`

Smoke tests útiles:

```bash
uv run python -m monofact.cli --help
```

```bash
uv run monofact auth-refresh --env homo
```

```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=20301231233 \
MONOFACT_PTO_VTA=2 \
uv run monofact config-check
```

```bash
uv run monofact invoice-list --env homo --cbte-nro 3
```

```bash
uv run monofact invoice-show --env homo --cbte-nro 3
```

Smoke end-to-end real en homologación:

```bash
./scripts/smoke_homo.sh
```

Nota: `scripts/smoke_homo.sh` emite una factura real en `homo`.

Import real de `pyafipws`:

```bash
uv run python -c "from pyafipws.wsfev1 import WSFEv1; print('WSFEv1 import ok')"
```

## Alcance actual de los tests

Los tests existentes no pegan a AFIP real.

Cubren:

- shape de respuestas JSON
- códigos de salida
- persistencia básica
- comportamiento del adapter con doubles/fakes
- aliases de `doc_tipo`
- listado local por número y rango de fechas
- detalle con AFIP primero y fallback local

No cubren:

- autenticación WSAA real
- credenciales reales de homologación o producción
- emisión real contra AFIP

## Cómo probar integración real

Necesitás `token` y `sign` válidos, además de `CUIT` y `pto_vta` correctos.

Si no querés pasar `token/sign` a mano, el camino preferido ahora es:

1. `uv run monofact auth-refresh --env homo`
2. `uv run monofact invoice-last --env homo`

Comando real validado para emitir en homologación:

```bash
uv run monofact invoice-create \
  --env homo \
  --doc-tipo consumidor-final \
  --doc-nro 0 \
  --imp-total 1000.00 \
  --cbte-fch 20260320 \
  --concepto 2
```

Ejemplos:

```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=<cuit> \
MONOFACT_PTO_VTA=<pto_vta> \
MONOFACT_TOKEN=<token> \
MONOFACT_SIGN=<sign> \
uv run monofact invoice-last
```

```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=<cuit> \
MONOFACT_PTO_VTA=<pto_vta> \
MONOFACT_TOKEN=<token> \
MONOFACT_SIGN=<sign> \
uv run monofact invoice-create \
  --doc-tipo 96 \
  --doc-nro 12345678 \
  --imp-total 1500.00 \
  --cbte-fch 20260301
```

## Ubicación de `pyafipws`

Checkout local esperado:

`/Users/andychapo/Projects/rocket-projects/pyafipws`

Si ese path cambia, hay que actualizar `pyproject.toml` en `[tool.uv.sources]`.

## Notas útiles para futuros agentes

- Preferir `uv run ...` en lugar de activar manualmente `.venv`.
- Si falla el import de `WSFEv1`, revisar primero `setuptools` y el path local de `pyafipws`.
- Si los tests pasan pero falla AFIP real, el problema probablemente esté en credenciales, conectividad SOAP, certificados, o configuración AFIP, no en la suite local.
- `uv run` puede reinstalar el paquete local editable; eso es esperable.
