#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PAYLOAD_DIR="$ROOT_DIR/payload"
TARGET_INPUT="${1:-/Applications/Cursor.app}"
TARGET_APP="$TARGET_INPUT"
finish(){ local status=$?; if [[ -t 0 ]]; then echo; read -r -p "按回车关闭窗口..." _; fi; exit "$status"; }
log(){ echo "[install-local-patch] $*"; }
resolve_cursor_app(){
  if [[ "$1" == *.app ]]; then
    printf "%s\n" "$1/Contents/Resources/app"
  else
    printf "%s\n" "$1"
  fi
}
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
is_protected_bundle_root(){
  case "$1" in
    "$HOME/Desktop"|"$HOME/Desktop/"*|"$HOME/Documents"|"$HOME/Documents/"*|"$HOME/Downloads"|"$HOME/Downloads/"*) return 0 ;;
  esac
  return 1
}
trap finish EXIT
TARGET_APP="$(resolve_cursor_app "$TARGET_INPUT")"
if [[ "${CURSOR_ZH_STAGED:-0}" != "1" ]] && is_protected_bundle_root "$ROOT_DIR"; then
  STAGE_ROOT="${TMPDIR:-/tmp}/cursor-zh-stage-$$"
  STAGE_DIR="$STAGE_ROOT/bundle"
  mkdir -p "$STAGE_ROOT"
  if command -v ditto >/dev/null 2>&1; then
    ditto "$ROOT_DIR" "$STAGE_DIR"
  else
    cp -R "$ROOT_DIR" "$STAGE_DIR"
  fi
  xattr -dr com.apple.quarantine "$STAGE_DIR" 2>/dev/null || true
  log "检测到补丁目录位于 macOS 受保护位置: $ROOT_DIR"
  log "已复制到临时目录后继续安装，以减少首次运行时的 Terminal 文件访问拦截。"
  exec env CURSOR_ZH_STAGED=1 "$STAGE_DIR/macOS/安装.command" "$TARGET_INPUT"
fi
xattr -dr com.apple.quarantine "$ROOT_DIR" 2>/dev/null || true
if [[ ! -d "$TARGET_APP" ]]; then
  echo "[install-local-patch] 未找到 Cursor 资源目录: $TARGET_APP" >&2
  exit 2
fi
if ! PYTHON_BIN="$(detect_python)"; then
  echo "[install-local-patch] 未找到 Python 3，请先安装 Python 3 再重试。" >&2
  exit 3
fi
export PYTHONPATH="$PAYLOAD_DIR${PYTHONPATH:+:$PYTHONPATH}"
"$PYTHON_BIN" -m cursor_zh apply --manifest "$PAYLOAD_DIR/patch_manifest.json" --cursor-app "$TARGET_APP" --enable-dynamic-market
