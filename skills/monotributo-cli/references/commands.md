# monofact command guide

Prefer the wrapper script for every invocation:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh <command> [args...]
```

Equivalent base command:

```bash
uv run monofact -v --format json <command> --env prod ...
```

## Read-only commands

Check resolved configuration:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh config-check
```

Refresh auth from the configured `pyafipws` production profile:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh auth-refresh
```

Read the last authorized voucher number from AFIP:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh invoice-last
```

List local SQLite records by voucher number:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh invoice-list --cbte-nro 123
```

List local SQLite records by date range:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh invoice-list --from 20260321 --to 20260321
```

Show one voucher, consulting AFIP first and also including the local record when it exists:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh invoice-show --cbte-nro 123
```

## Emission

Emit only when the user explicitly requested a live production invoice.

Common example for consumidor final:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh invoice-create \
  --doc-tipo consumidor-final \
  --doc-nro 0 \
  --imp-total 1000.00 \
  --cbte-fch 20260321
```

Useful `--doc-tipo` aliases in this repo:

- `dni`
- `cuit`
- `cuil`
- `consumidor-final`
- `cf`

For `--concepto 2` the CLI fills service dates automatically when missing.

`fecha_venc_pago` is not exposed as a CLI flag. The CLI fills it automatically with the execution date of the command. Example: on `2026-03-21`, emitting at that moment leaves `fecha_venc_pago=20260321`.
