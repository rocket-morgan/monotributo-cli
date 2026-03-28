# monotributo-cli

CLI para emitir Factura C (Monotributo). Esto es un wrapper del projecto `pyafipws`.

### Ejemplo
Emitir una factura de $1000 ARS por Servicios
```bash
uv run monofact invoice-create \
  --env homo \
  --doc-tipo consumidor-final \
  --doc-nro 0 \
  --imp-total 1000.00 \
  --cbte-fch 20260320 \
  --concepto 2
```

## Comandos
- `monofact config-check` Valida que la configuración esta ok
- `monofact auth-refresh` Renueva las credenciales de autenticación AFIP que usa pyafipws
- `monofact invoice-last` Trae ultima factura emitida
- `monofact invoice-create` Genera una nueva factura
- `monofact invoice-list` Lista todas las facturas, o bien trae las de un periodo especificado
- `monofact invoice-show` Muestra los detalles de factura especificada


## Formato de salida
- Por default el CLI responde en `json`
- También podés pedir salida humana en `yaml` o `yml` con un flag global

```bash
uv run monofact --format yaml config-check
```

## Skill para Agentes de AI
El repo incluye una skill reusable en [skills/monotributo-cli](/skills/monotributo-cli) para operar `monofact` desde Codex/Gemini/Claude/OpenClaw.

Defaults de la skill:

- `--env prod`
- `-v`
- `--format json`

Wrapper recomendada:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh config-check
```

## Setup local con uv
- Requiere `uv`
- Usa Python `3.14.3` vía `.python-version`
- Clona e instala `pyafipws` desde `https://github.com/reingart/pyafipws` en modo editable
- Auto-carga `.env` si existe en el directorio actual
- Precedencia de configuración: flags CLI > variables exportadas en shell > `.env` > defaults
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
MONOFACT_CUIT=201231233 \
MONOFACT_PTO_VTA=2 \
uv run monofact config-check
```

```bash
MONOFACT_ENV=homo \
MONOFACT_CUIT=201231233 \
MONOFACT_PTO_VTA=2 \
uv run monofact --format yaml config-check
```

También funciona sin exportar nada si `.env` ya contiene `MONOFACT_ENV`, `MONOFACT_CUIT` y `MONOFACT_PTO_VTA`.

### Emitir en homologación
Para `--doc-tipo 99` el CLI completa automáticamente `CondicionIVAReceptorId=5` (Consumidor Final).

`--doc-tipo` acepta tanto códigos AFIP como aliases legibles:

- `dni` -> `96`
- `cuit` -> `80`
- `cuil` -> `86`
- `consumidor-final` y `cf` -> `99`

Para `--concepto 2` completa automáticamente:

- `fecha_serv_desde` con `cbte_fch` si no se pasa `--fecha-serv-desde`
- `fecha_serv_hasta` con `cbte_fch` si no se pasa `--fecha-serv-hasta`
- `fecha_venc_pago` con la fecha actual de ejecución del comando

```bash
uv run monofact invoice-create \
  --env homo \
  --doc-tipo consumidor-final \
  --doc-nro 0 \
  --imp-total 1000.00 \
  --cbte-fch 20260320 \
  --concepto 2
```

```bash
uv run monofact --format yaml invoice-create \
  --env homo \
  --doc-tipo consumidor-final \
  --doc-nro 0 \
  --imp-total 1000.00 \
  --cbte-fch 20260320 \
  --concepto 2
```

### Listar y consultar facturas locales
`invoice-list` lee desde SQLite local (`MONOFACT_DB_PATH`) y filtra por `env` + `pto_vta` activos.

Buscar por número de comprobante:

```bash
uv run monofact invoice-list --env homo --cbte-nro 3
```

Buscar por rango de fechas:

```bash
uv run monofact invoice-list --env homo --from 20260320 --to 20260320
```

`invoice-show` busca una factura por número usando `env` + `pto_vta` activos, intenta consultar AFIP primero y además devuelve el registro local si existe.

```bash
uv run monofact invoice-show --env homo --cbte-nro 3
```

### Correr tests
```bash
uv run pytest -q
```

### Smoke test real en homologación
Hay un script reusable en [scripts/smoke_homo.sh](/scripts/smoke_homo.sh) que ejecuta:

- `config-check`
- `auth-refresh`
- `invoice-last`
- `invoice-create`
- `invoice-list --cbte-nro`
- `invoice-list --from/--to`
- `invoice-show`

Corre contra `homo` y emite una factura real de prueba en homologación.

```bash
./scripts/smoke_homo.sh
```

## Documentación
- `docs/specs-monotributo-v2.md`
