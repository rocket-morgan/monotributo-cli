# monotributo-cli

MVP CLI para emitir Factura C (Monotributo) reutilizando `pyafipws`.

## Estado
WIP (wrapper inicial V2).

## Comandos
- `monofact config-check`
- `monofact auth-refresh`
- `monofact invoice-last`
- `monofact invoice-create`

## Setup local con uv
- Requiere `uv`
- Usa Python `3.14.3` vía `.python-version`
- Instala `pyafipws` desde `../pyafipws` en modo editable
- Si faltan `MONOFACT_TOKEN` y `MONOFACT_SIGN`, intenta obtenerlos desde `pyafipws` según `--env`

### Inicializar entorno
```bash
uv sync --dev
```

### Autenticación desde pyafipws
Con `--env homo` usa `../pyafipws/conf/homologacion.ini`.

Con `--env prod` usa `../pyafipws/conf/produccion.ini`.

```bash
uv run monofact auth-refresh --env homo
```

### Verificar CLI
```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=20123456789 \
MONOFACT_PTO_VTA=1 \
uv run monofact config-check
```

### Correr tests
```bash
uv run pytest -q
```

## Documentación
- `docs/specs-monotributo-v1.md`
- `docs/specs-monotributo-v2.md`
