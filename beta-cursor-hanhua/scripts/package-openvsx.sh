#!/bin/zsh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"
export npm_config_cache="$ROOT_DIR/.npm-cache"
npx -y @vscode/vsce package --allow-missing-repository
