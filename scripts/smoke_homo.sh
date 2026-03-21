#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

if ! command -v uv >/dev/null 2>&1; then
  echo "error: uv no está instalado o no está en PATH" >&2
  exit 1
fi

TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT INT TERM HUP

SMOKE_DATE=${MONOFACT_SMOKE_DATE:-$(date +%Y%m%d)}
SMOKE_AMOUNT=${MONOFACT_SMOKE_AMOUNT:-1000.00}

run_output() {
  format=$1
  name=$2
  shift 2
  outfile="$TMP_DIR/$name.$format"
  echo "== $name ($format)"
  output=$("$@")
  printf '%s\n' "$output"
  printf '%s\n' "$output" > "$outfile"
}

run_output json config-check uv run monofact --format json config-check --env homo
uv run python - json "$TMP_DIR/config-check.json" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["env"] == "homo", data
assert int(data["pto_vta"]) > 0, data
PY

run_output yaml config-check uv run monofact --format yaml config-check --env homo
uv run python - yaml "$TMP_DIR/config-check.yaml" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["env"] == "homo", data
assert int(data["pto_vta"]) > 0, data
PY

run_output json auth-refresh uv run monofact --format json auth-refresh --env homo
uv run python - json "$TMP_DIR/auth-refresh.json" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["env"] == "homo", data
PY

run_output yaml auth-refresh uv run monofact --format yaml auth-refresh --env homo
uv run python - yaml "$TMP_DIR/auth-refresh.yaml" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["env"] == "homo", data
PY

run_output json invoice-last uv run monofact --format json invoice-last --env homo
uv run python - json "$TMP_DIR/invoice-last.json" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["tipo_comp"] == 11, data
assert int(data["pto_vta"]) > 0, data
PY

run_output yaml invoice-last uv run monofact --format yaml invoice-last --env homo
uv run python - yaml "$TMP_DIR/invoice-last.yaml" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["tipo_comp"] == 11, data
assert int(data["pto_vta"]) > 0, data
PY

run_output json invoice-create \
  uv run monofact --format json invoice-create \
    --env homo \
    --doc-tipo consumidor-final \
    --doc-nro 0 \
    --imp-total "$SMOKE_AMOUNT" \
    --cbte-fch "$SMOKE_DATE"

uv run python - json "$TMP_DIR/invoice-create.json" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["resultado"] == "A", data
assert int(data["cbte_nro"]) > 0, data
assert int(data["record_id"]) > 0, data
assert data["cae"], data
PY

CBTE_NRO=$(uv run python - "$TMP_DIR/invoice-create.json" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    data = json.load(fh)
print(data["cbte_nro"])
PY
)

run_output json invoice-list-by-number uv run monofact --format json invoice-list --env homo --cbte-nro "$CBTE_NRO"
uv run python - json "$TMP_DIR/invoice-list-by-number.json" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
cbte_nro = int(sys.argv[3])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["count"] >= 1, data
assert any(int(item["cbte_nro"]) == cbte_nro for item in data["items"]), data
PY

run_output yaml invoice-list-by-number uv run monofact --format yaml invoice-list --env homo --cbte-nro "$CBTE_NRO"
uv run python - yaml "$TMP_DIR/invoice-list-by-number.yaml" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
cbte_nro = int(sys.argv[3])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["count"] >= 1, data
assert any(int(item["cbte_nro"]) == cbte_nro for item in data["items"]), data
PY

run_output json invoice-list-by-date uv run monofact --format json invoice-list --env homo --from "$SMOKE_DATE" --to "$SMOKE_DATE"
uv run python - json "$TMP_DIR/invoice-list-by-date.json" "$SMOKE_DATE" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
smoke_date = sys.argv[3]
cbte_nro = int(sys.argv[4])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["count"] >= 1, data
assert any(item["cbte_fch"] == smoke_date and int(item["cbte_nro"]) == cbte_nro for item in data["items"]), data
PY

run_output yaml invoice-list-by-date uv run monofact --format yaml invoice-list --env homo --from "$SMOKE_DATE" --to "$SMOKE_DATE"
uv run python - yaml "$TMP_DIR/invoice-list-by-date.yaml" "$SMOKE_DATE" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
smoke_date = sys.argv[3]
cbte_nro = int(sys.argv[4])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["count"] >= 1, data
assert any(item["cbte_fch"] == smoke_date and int(item["cbte_nro"]) == cbte_nro for item in data["items"]), data
PY

run_output json invoice-show uv run monofact --format json invoice-show --env homo --cbte-nro "$CBTE_NRO"
uv run python - json "$TMP_DIR/invoice-show.json" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
cbte_nro = int(sys.argv[3])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["source"] in {"afip", "local"}, data
assert int(data["cbte_nro"]) == cbte_nro, data
if data["source"] == "afip":
    assert data["afip"] is not None, data
    assert int(data["afip"]["cbte_nro"]) == cbte_nro, data
if data.get("local") is not None:
    assert int(data["local"]["cbte_nro"]) == cbte_nro, data
PY

run_output yaml invoice-show uv run monofact --format yaml invoice-show --env homo --cbte-nro "$CBTE_NRO"
uv run python - yaml "$TMP_DIR/invoice-show.yaml" "$CBTE_NRO" <<'PY'
import json, sys, yaml
fmt, path = sys.argv[1], sys.argv[2]
cbte_nro = int(sys.argv[3])
with open(path, encoding="utf-8") as fh:
    data = json.load(fh) if fmt == "json" else yaml.safe_load(fh)
assert data["ok"] is True, data
assert data["source"] in {"afip", "local"}, data
assert int(data["cbte_nro"]) == cbte_nro, data
if data["source"] == "afip":
    assert data["afip"] is not None, data
    assert int(data["afip"]["cbte_nro"]) == cbte_nro, data
if data.get("local") is not None:
    assert int(data["local"]["cbte_nro"]) == cbte_nro, data
PY

echo "Smoke homo OK para cbte_nro=$CBTE_NRO fecha=$SMOKE_DATE"
