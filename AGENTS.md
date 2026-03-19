# AGENTS.md

## Resumen rápido

`monotributo-cli` es un CLI Python para emitir Factura C de Monotributo usando `pyafipws` como librería embebida, no como servicio externo.

Comandos principales:

- `monofact config-check`
- `monofact invoice-last`
- `monofact invoice-create`

El entrypoint del CLI está en `monofact/cli.py`.

## Estructura del repo

- `monofact/cli.py`: comandos Click, validaciones, códigos de salida, salida JSON.
- `monofact/config.py`: carga de configuración desde flags y variables de entorno.
- `monofact/afip_adapter.py`: wrapper sobre `pyafipws.wsfev1.WSFEv1`.
- `monofact/storage.py`: persistencia SQLite de requests/responses.
- `tests/test_cli_contract.py`: contrato de payloads JSON del CLI.
- `tests/test_cli_integration.py`: tests de integración del CLI usando fake adapter.
- `tests/test_afip_adapter.py`: tests unitarios del adapter con fake WS.
- `docs/specs-monotributo-v1.md` y `docs/specs-monotributo-v2.md`: specs del proyecto.

## Dependencias y entorno

El proyecto usa `uv`.

Setup actual:

- Python pinneado en `.python-version`: `3.14.3`
- lockfile: `uv.lock`
- `pyafipws` se instala desde el checkout local `../pyafipws`
- `pyafipws` está configurado como dependencia editable en `pyproject.toml`

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

Flujo de `invoice-last`:

1. `cli.py` carga settings desde flags/env.
2. Instancia `AFIPAdapter`.
3. `AFIPAdapter` importa `WSFEv1`, conecta al WSDL y consulta el último comprobante.
4. El CLI devuelve JSON a stdout.

Flujo de `invoice-create`:

1. `cli.py` valida `imp_total` y completa `cbte_fch` si falta.
2. Construye `InvoiceInput`.
3. `AFIPAdapter.emit_factura_c()` consulta último comprobante, calcula el siguiente y llama `CrearFactura()` + `CAESolicitar()`.
4. `storage.py` persiste request y response en SQLite.
5. El CLI devuelve JSON con `record_id`.

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
- `MONOFACT_WSFE_HOMO`
- `MONOFACT_WSFE_PROD`

Template base: `.env.example`

## Qué requiere `pyafipws`

Punto clave:

- `config-check` no necesita importar `pyafipws`
- `invoice-last` y `invoice-create` sí necesitan `pyafipws`

El CLI no levanta `pyafipws` como proceso aparte y no consume Docker ni HTTP intermedio. Todo corre dentro del mismo proceso Python.

## Cómo testear

Suite completa:

```bash
uv run pytest -q
```

Estado conocido al momento de escribir este archivo:

- `15 passed`

Smoke tests útiles:

```bash
uv run python -m monofact.cli --help
```

```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=20123456789 \
MONOFACT_PTO_VTA=1 \
MONOFACT_TOKEN=test-token \
MONOFACT_SIGN=test-sign \
uv run monofact config-check
```

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

No cubren:

- autenticación WSAA real
- credenciales reales de homologación o producción
- emisión real contra AFIP

## Cómo probar integración real

Necesitás `token` y `sign` válidos, además de `CUIT` y `pto_vta` correctos.

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
