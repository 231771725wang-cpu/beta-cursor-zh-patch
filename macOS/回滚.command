#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PAYLOAD_DIR="$ROOT_DIR/payload"
finish(){ local status=$?; if [[ -t 0 ]]; then echo; read -r -p "按回车关闭窗口..." _; fi; exit "$status"; }
detect_python(){
  local candidate
  for candidate in python3 /usr/bin/python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf "%s\n" "$candidate"
      return 0
    fi
  done
  return 1
}
trap finish EXIT
xattr -dr com.apple.quarantine "$ROOT_DIR" 2>/dev/null || true
if ! PYTHON_BIN="$(detect_python)"; then
  echo "[rollback-local-patch] 未找到 Python 3，请先安装 Python 3 再重试。" >&2
  exit 3
fi
export PYTHONPATH="$PAYLOAD_DIR${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m cursor_zh rollback --state "$PAYLOAD_DIR/.cursor_zh_state/last_apply.json"
