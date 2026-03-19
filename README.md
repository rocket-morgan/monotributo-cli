# monotributo-cli

MVP CLI para emitir Factura C (Monotributo) reutilizando `pyafipws`.

## Estado
WIP (wrapper inicial V2).

## Comandos
- `monofact config-check`
- `monofact invoice-last`
- `monofact invoice-create`

## Setup local con uv
- Requiere `uv`
- Usa Python `3.14.3` vía `.python-version`
- Instala `pyafipws` desde `../pyafipws` en modo editable

### Inicializar entorno
```bash
uv sync --dev
```

### Verificar CLI
```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=20123456789 \
MONOFACT_PTO_VTA=1 \
MONOFACT_TOKEN=test-token \
MONOFACT_SIGN=test-sign \
uv run monofact config-check
```

### Correr tests
```bash
uv run pytest -q
```

## Documentación
- `docs/specs-monotributo-v1.md`
- `docs/specs-monotributo-v2.md`
