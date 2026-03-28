---
name: monotributo-cli
description: Operate the `monofact` CLI in this repository for AFIP Monotributo workflows. Use when Codex needs to run `config-check`, `auth-refresh`, `invoice-last`, `invoice-list`, `invoice-show`, or `invoice-create` against the local `monotributo-cli` project. Default to production (`--env prod`), JSON output (`--format json`), and verbose mode (`-v`).
---

# Monotributo CLI

Use this skill from the repository root. Prefer the bundled wrapper:

```bash
bash ./skills/monotributo-cli/scripts/run_monofact_prod.sh <command> [args...]
```

The wrapper:

- runs `uv run monofact`
- adds `-v --format json`
- defaults to `--env prod` unless the caller already passed `--env`

## Workflow

1. Start with read-only commands when the user is diagnosing or verifying setup:
   - `config-check`
   - `auth-refresh`
   - `invoice-last`
   - `invoice-list`
   - `invoice-show`
2. Run `invoice-create` only when the user explicitly asked to emit a real invoice.
3. Keep `--env prod` as the default. Override to `--env homo` only when the user explicitly wants homologation.
4. Return the important JSON fields in the answer instead of saying only that the command succeeded.

## Common Commands

Read [references/commands.md](references/commands.md) for the command shapes this repo currently supports.

## Guardrails

- Treat production as live AFIP traffic.
- Do not switch to YAML unless the user asks.
- Do not drop verbose mode unless the user asks.
- For service invoices, remember that `fecha_venc_pago` is not passed as a CLI flag. The CLI fills it automatically with the command execution date. Example: if today is `2026-03-21`, emitting now will leave `fecha_venc_pago=20260321`.
- `invoice-list` reads the local SQLite history; `invoice-show` tries AFIP first and also includes the local record when available.
- If a command fails, include the `message`, `errors`, `obs`, exit behavior, and the exact command you ran.
