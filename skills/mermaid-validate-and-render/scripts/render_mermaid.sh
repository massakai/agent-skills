#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 || $# -gt 4 ]]; then
  echo "Usage: scripts/render_mermaid.sh <input.mmd> <output.svg> [mermaid-config.json] [puppeteer-config.json]" >&2
  exit 1
fi

input_file="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
output_file="$2"
config_file="${3:-}"
puppeteer_config_file="${4:-${PUPPETEER_CONFIG_FILE:-}}"
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
local_mmdc="$script_dir/../node_modules/.bin/mmdc"

if [[ -n "${MMDC:-}" ]]; then
  cmd=("$MMDC")
elif command -v mmdc >/dev/null 2>&1; then
  cmd=("$(command -v mmdc)")
elif [[ -x "$local_mmdc" ]]; then
  cmd=("$local_mmdc")
else
  echo "ERROR: mmdc not found. Install @mermaid-js/mermaid-cli or set MMDC." >&2
  exit 127
fi

args=("${cmd[@]}" -i "$input_file" -o "$output_file" -b transparent)

if [[ -n "$config_file" ]]; then
  args+=(-c "$config_file")
fi

if [[ -n "$puppeteer_config_file" ]]; then
  args+=(-p "$puppeteer_config_file")
fi

"${args[@]}"
echo "OK: render succeeded for $input_file -> $output_file"
