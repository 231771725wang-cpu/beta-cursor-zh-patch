#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
export npm_config_cache="$ROOT_DIR/.npm-cache"
TOKEN="${OPEN_VSX_TOKEN:-}"
if [[ -z "$TOKEN" ]]; then
  echo "缺少 OPEN_VSX_TOKEN 环境变量" >&2
  exit 1
fi
VSIX="$(ls -t ./*.vsix 2>/dev/null | head -n 1 || true)"
if [[ -z "$VSIX" ]]; then
  npx -y @vscode/vsce package
  VSIX="$(ls -t ./*.vsix | head -n 1)"
fi
npx -y ovsx publish "$VSIX" -p "$TOKEN"
