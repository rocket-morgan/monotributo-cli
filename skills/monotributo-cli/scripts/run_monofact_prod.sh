#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/../../.." && pwd)
cd "$ROOT_DIR"

if [ "$#" -lt 1 ]; then
  echo "usage: ./skills/monotributo-cli/scripts/run_monofact_prod.sh <command> [args...]" >&2
  exit 2
fi

command_name=$1
shift

has_env=0
for arg in "$@"; do
  case "$arg" in
    --env|--env=*)
      has_env=1
      ;;
  esac
done

if [ "$has_env" -eq 1 ]; then
  exec uv run monofact -v --format json "$command_name" "$@"
fi

exec uv run monofact -v --format json "$command_name" --env prod "$@"
