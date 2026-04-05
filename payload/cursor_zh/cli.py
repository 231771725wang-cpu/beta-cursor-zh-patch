#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import shutil
import sys
import zipfile
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARTIFACTS_DIR = ROOT / "artifacts"
STATE_DIR = ROOT / ".cursor_zh_state"
STORE_EXTENSION_DIR = ROOT / "beta-cursor-private-zh-overlay"

SCAN_DIR = ARTIFACTS_DIR / "scan"
PATCH_MANIFEST_DIR = ARTIFACTS_DIR / "patch_manifest"
QA_DIR = ARTIFACTS_DIR / "qa"
BACKUP_DIR = ARTIFACTS_DIR / "backups"
COVERAGE_DIR = ARTIFACTS_DIR / "coverage_report"
UPGRADE_DIR = ARTIFACTS_DIR / "upgrade"
STORE_EXTENSION_ARTIFACTS_DIR = ARTIFACTS_DIR / "store_extension"
LOCAL_BUNDLE_DIR = ARTIFACTS_DIR / "local_bundle"

DEFAULT_CURSOR_APP = Path("/Applications/Cursor.app/Contents/Resources/app")
DEFAULT_LANG_EXT_ROOT = Path.home() / ".cursor" / "extensions"
STORE_EXTENSION_OVERRIDES_PATH = DATA_DIR / "translations" / "store_extension_overrides.json"

PH_RE = re.compile(r"\{[0-9]+\}")
EN_RE = re.compile(r"[A-Za-z][A-Za-z0-9&/().,:;'\-+ ]{2,}")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
IDENTIFIER_LIKE_RE = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$.-]*$")
WORKBENCH_USER_VISIBLE_LITERAL_RE = re.compile(
    r'(?:label|title|placeholder|description|text|hint|aria-label)\s*:\s*"((?:\\.|[^"\\]){4,200})"'
)
DYNAMIC_MARKET_MARK_BEGIN = "/* CURSOR_ZH_DYNAMIC_MARKET_BEGIN v1 */"
DYNAMIC_MARKET_MARK_END = "/* CURSOR_ZH_DYNAMIC_MARKET_END v1 */"
DYNAMIC_MARKET_TARGET_REL = Path("out/vs/workbench/workbench.desktop.main.js")
INTEGRITY_SERVICE_ORIGINAL = (
    "async _isPure(){const e=this.productService.checksums||{};await this.lifecycleService.when(4);"
    "const t=await Promise.all(Object.keys(e).map(r=>this._resolve(r,e[r])));let i=!0;"
    "for(let r=0,s=t.length;r<s;r++)if(!t[r].isPure){i=!1;break}return{isPure:i,proof:t}}"
)
INTEGRITY_SERVICE_PATCHED = "async _isPure(){return{isPure:!0,proof:[]}}"
STATIC_REPLACEMENT_BLOCKLIST = {
    "out/main.js",
}
AGENT_MENU_CONTEXTUAL_REPLACEMENTS = (
    {
        "id": "agent_mode_menu",
        "source": 'AnA=[{mode:"off",label:"Off"},{mode:"auto",label:"Auto"},{mode:"on",label:"On"}]',
        "target": 'AnA=[{mode:"off",label:"关闭"},{mode:"auto",label:"自动"},{mode:"on",label:"开启"}]',
    },
    {
        "id": "agent_archive_filter_menu",
        "source": 'ilS=[{mode:"only_unread",label:"仅未读",icon:"bell"},{mode:"only_archived",label:"仅已归档",icon:"archive"},{mode:"include_archived",label:"包含已归档",icon:"layers"},{mode:"off",label:"Off",icon:"circle"}]',
        "target": 'ilS=[{mode:"only_unread",label:"仅未读",icon:"bell"},{mode:"only_archived",label:"仅已归档",icon:"archive"},{mode:"include_archived",label:"包含已归档",icon:"layers"},{mode:"off",label:"关闭",icon:"circle"}]',
    },
)


@dataclass
class CursorContext:
    app_path: Path
    package_path: Path
    product_path: Path
    version: str
    commit: str
    lang_pack_path: Path | None


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in (
        ARTIFACTS_DIR,
        STATE_DIR,
        SCAN_DIR,
        PATCH_MANIFEST_DIR,
        QA_DIR,
        BACKUP_DIR,
        COVERAGE_DIR,
        UPGRADE_DIR,
        STORE_EXTENSION_ARTIFACTS_DIR,
        LOCAL_BUNDLE_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_executable_text(path: Path, content: str) -> None:
    write_text(path, content)
    path.chmod(0o755)


def relative_target_path(app_path: Path, path: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(app_path.resolve(strict=False)).as_posix()
    except ValueError:
        return None


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_file_base64(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode("ascii")


def detect_lang_pack() -> Path | None:
    if not DEFAULT_LANG_EXT_ROOT.exists():
        return None
    candidates = sorted(
        DEFAULT_LANG_EXT_ROOT.glob("ms-ceintl.vscode-language-pack-zh-hans-*-universal"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def detect_cursor_context(cursor_app: Path | None = None) -> CursorContext:
    app_path = cursor_app or DEFAULT_CURSOR_APP
    package_path = app_path / "package.json"
    product_path = app_path / "product.json"
    if not app_path.exists():
        raise FileNotFoundError(f"未找到 Cursor 应用目录: {app_path}")
    if not package_path.exists():
        raise FileNotFoundError(f"未找到 package.json: {package_path}")
    if not product_path.exists():
        raise FileNotFoundError(f"未找到 product.json: {product_path}")
    package = read_json(package_path)
    product = read_json(product_path)
    version = str(package.get("version", "unknown"))
    commit = str(product.get("commit", "unknown"))
    return CursorContext(
        app_path=app_path,
        package_path=package_path,
        product_path=product_path,
        version=version,
        commit=commit,
        lang_pack_path=detect_lang_pack(),
    )


def load_custom_phrases() -> dict[str, str]:
    return read_json(DATA_DIR / "translations" / "custom_phrases.json")


def load_forced_terms() -> dict[str, str]:
    return read_json(DATA_DIR / "glossary" / "forced_terms.json")


def load_keep_english_terms() -> list[str]:
    return read_json(DATA_DIR / "glossary" / "keep_english_terms.json")


def load_forbidden_terms() -> list[str]:
    return read_json(DATA_DIR / "glossary" / "forbidden_terms.json")


def load_core_phrases() -> list[str]:
    return read_json(DATA_DIR / "coverage" / "core_phrases.json")


def load_dynamic_market_phrases() -> dict[str, str]:
    path = DATA_DIR / "translations" / "dynamic_market_phrases.json"
    if not path.exists():
        return {}
    return read_json(path)


def load_store_extension_overrides() -> dict[str, dict[str, str]]:
    if not STORE_EXTENSION_OVERRIDES_PATH.exists():
        return {}
    return read_json(STORE_EXTENSION_OVERRIDES_PATH)


def discover_store_extension_targets(ctx: CursorContext) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for package_nls_path in sorted((ctx.app_path / "extensions").glob("cursor-*/package.nls.json")):
        package_path = package_nls_path.with_name("package.json")
        if not package_path.exists():
            continue
        package = read_json(package_path)
        publisher = str(package.get("publisher", "")).strip()
        name = str(package.get("name", "")).strip()
        if not publisher or not name:
            continue
        targets.append(
            {
                "extension_id": f"{publisher}.{name}",
                "extension_dir": str(package_path.parent),
                "package_path": str(package_path),
                "package_nls_path": str(package_nls_path),
            }
        )
    return targets


def discover_store_extension_blocked_targets(ctx: CursorContext) -> list[dict[str, str]]:
    blocked: list[dict[str, str]] = []
    extensions_root = ctx.app_path / "extensions"
    for package_path in sorted(extensions_root.glob("cursor-*/package.json")):
        package_nls_path = package_path.with_name("package.nls.json")
        if package_nls_path.exists():
            continue
        package = read_json(package_path)
        publisher = str(package.get("publisher", "")).strip()
        name = str(package.get("name", "")).strip()
        if not publisher or not name:
            continue
        blocked.append(
            {
                "extension_id": f"{publisher}.{name}",
                "package_path": str(package_path),
                "reason": "missing_package_nls",
            }
        )
    return blocked


def build_store_extension_readme(
    ctx: CursorContext,
    report: dict[str, Any],
    package_name: str,
    package_display_name: str,
) -> str:
    translated_targets = [item for item in report["targets"] if item["translated_keys"] > 0]
    blocked_targets = report.get("blocked_targets", [])
    lines = [
        f"# {package_display_name}",
        "",
        "这是一个实验性的 Cursor 私有扩展汉化覆盖层，用于补充标准本地化接口可见的 Cursor 私有扩展文案。",
        "",
        "它不是仓库主产物，也不等价于本仓库的本地完整汉化补丁。",
        "",
        "## 能力边界",
        "",
        "- 仅覆盖 Cursor 自带私有扩展里已经暴露到 `package.nls.json` 的文案。",
        "- 不修改 Cursor.app 主程序文件，适合打包为 VSIX 或作为实验性附属产物分发。",
        "- 不覆盖 `workbench.desktop.main.js` 等主程序硬编码文案；这部分仍需仓库根目录的 `cursor-zh apply` 补丁链处理。",
        "",
        "## 当前生成信息",
        "",
        f"- 目标 Cursor 版本: `{ctx.version}`",
        f"- 目标提交哈希: `{ctx.commit}`",
        f"- 扩展名: `{package_name}`",
        f"- 已生成本地化目标: `{len(translated_targets)}` 个",
        f"- 无法导出到该覆盖层的 Cursor 内置扩展: `{len(blocked_targets)}` 个",
        "",
        "## 已覆盖的 Cursor 内置扩展",
        "",
    ]
    if translated_targets:
        for item in translated_targets:
            lines.append(f"- `{item['extension_id']}`: {item['translated_keys']} 个键")
    else:
        lines.append("- 当前未发现可导出的 Cursor 私有扩展本地化键。")
    lines.extend(
        [
            "",
            "## 安装方式",
            "",
            "1. 安装本扩展的 `.vsix`，然后重载 Cursor。",
            "2. 若仍有未汉化区域，说明它属于 Cursor 主程序硬编码文案或未暴露到标准本地化接口的私有界面，请改用本仓库根目录的完整补丁链。",
            "3. 如果你还想补齐 Cursor / VS Code 公共界面的通用简体中文，可额外叠加官方简体中文语言包，但这不是本扩展的前置条件。",
            "",
            "## 当前无法直接做成覆盖层的内置扩展",
            "",
        ]
    )
    if blocked_targets:
        for item in blocked_targets:
            lines.append(f"- `{item['extension_id']}`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造")
    else:
        lines.append("- 当前未发现受阻的 Cursor 私有扩展。")
    lines.extend(
        [
            "",
            "## 重新生成",
            "",
            "```bash",
            "./cursor-zh export-store-extension",
            "```",
            "",
            "可选参数：",
            "",
            "- `--publisher your-openvsx-namespace`",
            "- `--version 0.1.0`",
            "- `--output-dir ./beta-cursor-private-zh-overlay`",
            "",
            "## 打包与发布",
            "",
            "```bash",
            "cd beta-cursor-private-zh-overlay",
            "./scripts/package-openvsx.sh",
            "OPEN_VSX_TOKEN=xxxx ./scripts/publish-openvsx.sh",
            "```",
            "",
            "## 边界说明",
            "",
            "- 该覆盖层只承载标准本地化接口可见的文案。",
            "- 直接改主程序 JS 的完整汉化部分，不能等价迁移成纯语言包或纯覆盖层。",
            "- 如需接近本仓库当前覆盖率，应优先使用仓库根目录的本地完整补丁版。",
            "- `beta-cursor-private-zh-overlay/`：实验性私有扩展汉化覆盖层。",
            "- 仓库根目录 `cursor-zh`：本地完整补丁版。",
            "",
        ]
    )
    return "\n".join(lines)


def write_store_extension_package(
    ctx: CursorContext,
    output_dir: Path,
    publisher: str,
    version: str,
    package_name: str,
    package_display_name: str,
    localization_entries: list[dict[str, str]],
) -> None:
    vscode_engine = "^1.105.0"
    if ctx.lang_pack_path:
        package_json = ctx.lang_pack_path / "package.json"
        if package_json.exists():
            try:
                lang_pack = read_json(package_json)
                version_hint = str(lang_pack.get("version", "")).strip()
                if version_hint:
                    vscode_engine = f"^{version_hint}"
            except Exception:
                pass
    package = {
        "name": package_name,
        "displayName": package_display_name,
        "description": "Experimental Chinese overlay for Cursor private extensions. 实验性补充 Cursor 私有扩展简体中文界面。",
        "version": version,
        "publisher": publisher,
        "license": "MIT",
        "icon": "media/icon.png",
        "engines": {"vscode": vscode_engine},
        "categories": ["Language Packs"],
        "keywords": ["cursor", "chinese", "zh-cn", "overlay", "private-extension", "hanhua"],
        "galleryBanner": {"color": "#0b1836", "theme": "dark"},
        "files": [
            "media/**",
            "translations/**",
            "README.md",
            "CHANGELOG.md",
            "LICENSE",
            "package.json",
        ],
        "scripts": {
            "package:openvsx": "bash ./scripts/package-openvsx.sh",
            "publish:openvsx": "bash ./scripts/publish-openvsx.sh",
        },
        "contributes": {
            "localizations": [
                {
                    "languageId": "zh-cn",
                    "languageName": "Chinese Simplified",
                    "localizedLanguageName": "中文(简体)",
                    "translations": localization_entries,
                }
            ]
        },
    }
    write_json(output_dir / "package.json", package)


def run_export_store_extension(
    ctx: CursorContext,
    output_dir: Path | None = None,
    publisher: str = "beta-cursor",
    version: str = "0.1.0",
    package_name: str = "beta-cursor-private-zh-overlay",
    package_display_name: str = "Beta Cursor 私有扩展汉化覆盖层（实验）",
) -> dict[str, Any]:
    ensure_dirs()
    output_root = output_dir or STORE_EXTENSION_DIR
    translations_dir = output_root / "translations" / "extensions"
    translations_dir.mkdir(parents=True, exist_ok=True)

    custom_phrases = load_custom_phrases()
    overrides = load_store_extension_overrides()
    targets = discover_store_extension_targets(ctx)
    blocked_targets = discover_store_extension_blocked_targets(ctx)

    localization_entries: list[dict[str, str]] = []
    report_targets: list[dict[str, Any]] = []
    keep_files: set[str] = set()

    for target in targets:
        extension_id = target["extension_id"]
        package_nls = read_json(Path(target["package_nls_path"]))
        override_map = overrides.get(extension_id, {})
        translated: dict[str, str] = {}
        missing: list[dict[str, str]] = []

        for key, source in package_nls.items():
            translated_text = override_map.get(key) or custom_phrases.get(source)
            if translated_text and translated_text != source:
                translated[key] = translated_text
            else:
                missing.append({"key": key, "source": source})

        file_name = f"{extension_id}.i18n.json"
        report_targets.append(
            {
                **target,
                "translated_keys": len(translated),
                "missing_keys": missing,
                "output_file": str(translations_dir / file_name) if translated else None,
            }
        )
        if not translated:
            continue

        keep_files.add(file_name)
        write_json(
            translations_dir / file_name,
            {
                "version": "1.0.0",
                "contents": {
                    "package": translated,
                },
            },
        )
        localization_entries.append(
            {
                "id": extension_id,
                "path": f"./translations/extensions/{file_name}",
            }
        )

    for existing in translations_dir.glob("*.i18n.json"):
        if existing.name not in keep_files:
            existing.unlink()

    write_store_extension_package(
        ctx=ctx,
        output_dir=output_root,
        publisher=publisher,
        version=version,
        package_name=package_name,
        package_display_name=package_display_name,
        localization_entries=localization_entries,
    )
    write_store_extension_assets(output_root)
    write_text(
        output_root / "README.md",
        build_store_extension_readme(
            ctx=ctx,
            report={"targets": report_targets, "blocked_targets": blocked_targets},
            package_name=package_name,
            package_display_name=package_display_name,
        ),
    )
    write_text(
        output_root / "CHANGELOG.md",
        "\n".join(
            [
                "# Changelog",
                "",
                "## 0.1.0",
                "",
                f"- 初始导出，适配 Cursor {ctx.version}。",
                "- 首次导出实验性私有扩展汉化覆盖层。",
                "- 覆盖标准本地化接口可见的 Cursor 私有扩展文案，不依赖官方简体中文语言包作为安装前提。",
                "",
            ]
        ),
    )

    report = {
        "generated_at": now_iso(),
        "cursor": {
            "app_path": str(ctx.app_path),
            "version": ctx.version,
            "commit": ctx.commit,
            "lang_pack_path": str(ctx.lang_pack_path) if ctx.lang_pack_path else None,
        },
        "output_dir": str(output_root),
        "package_name": package_name,
        "publisher": publisher,
        "version": version,
        "targets": report_targets,
        "blocked_targets": blocked_targets,
        "summary": {
            "target_extensions": len(targets),
            "localized_extensions": len(localization_entries),
            "translated_keys": sum(item["translated_keys"] for item in report_targets),
            "missing_keys": sum(len(item["missing_keys"]) for item in report_targets),
            "blocked_extensions": len(blocked_targets),
        },
    }
    write_json(STORE_EXTENSION_ARTIFACTS_DIR / "latest.json", report)
    return report


def is_blocked_static_target(path: Path) -> bool:
    normalized = path.as_posix()
    return any(normalized.endswith(rel) for rel in STATIC_REPLACEMENT_BLOCKLIST)


def is_safe_static_phrase_for_path(path: Path, phrase: str) -> bool:
    text = phrase.strip()
    if not text:
        return False
    if path.suffix != ".js":
        return True
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return True
    return IDENTIFIER_LIKE_RE.fullmatch(text) is None


def iter_cursor_targets(ctx: CursorContext) -> list[Path]:
    targets: list[Path] = []
    fixed = [
        ctx.app_path / "out" / "nls.messages.json",
        ctx.app_path / "out" / "vs" / "workbench" / "workbench.desktop.main.js",
    ]
    for path in fixed:
        if path.exists():
            targets.append(path)
    targets.extend(sorted((ctx.app_path / "extensions").glob("cursor-*/package.json")))
    return targets


def english_literals_from_package_json(path: Path, limit: int = 30) -> list[str]:
    try:
        data = read_json(path)
    except Exception:
        return []
    values: list[str] = []

    def walk(node: Any) -> None:
        if len(values) >= limit:
            return
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
            return
        if isinstance(node, list):
            for value in node:
                walk(value)
            return
        if isinstance(node, str):
            if CJK_RE.search(node):
                return
            if "http://" in node or "https://" in node:
                return
            if len(node) < 4:
                return
            if EN_RE.search(node):
                values.append(node.strip())

    walk(data)
    return values[:limit]


def is_user_visible_english_literal(literal: str, *, allow_single_word: bool = False) -> bool:
    text = literal.strip()
    if len(text) < 4 or len(text) > 160:
        return False
    if CJK_RE.search(text):
        return False
    if "\n" in text or "\r" in text or "\t" in text:
        return False
    if "http://" in text or "https://" in text:
        return False
    if text.startswith("$(") or text.endswith(".json"):
        return False
    if IDENTIFIER_LIKE_RE.fullmatch(text):
        return False
    if re.search(r"[{}<>`]", text):
        return False
    if re.search(r"(^|[^A-Za-z])(on[A-Z][A-Za-z0-9]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+)($|[^A-Za-z])", text):
        return False
    words = re.findall(r"[A-Za-z]+", text)
    if not words:
        return False
    if len(words) == 1 and not allow_single_word:
        return False
    return EN_RE.search(text) is not None


def english_literals_from_nls_messages(content: str, limit: int = 30) -> list[str]:
    try:
        values = json.loads(content)
    except Exception:
        return []
    if not isinstance(values, list):
        return []
    results: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if not is_user_visible_english_literal(text, allow_single_word=True):
            continue
        if text in seen:
            continue
        seen.add(text)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def english_literals_from_workbench_bundle(content: str, limit: int = 30) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for match in WORKBENCH_USER_VISIBLE_LITERAL_RE.finditer(content):
        raw = match.group(1)
        try:
            text = json.loads(f'"{raw}"')
        except Exception:
            text = raw
        text = text.strip()
        if not is_user_visible_english_literal(text, allow_single_word=True):
            continue
        if text in seen:
            continue
        seen.add(text)
        results.append(text)
        if len(results) >= limit:
            break
    return results


def sample_english_literals_for_path(path: Path, content: str, limit: int = 30) -> list[str]:
    if path.name == "package.json":
        return english_literals_from_package_json(path, limit=limit)
    if path.name == "nls.messages.json":
        return english_literals_from_nls_messages(content, limit=limit)
    if path.name == DYNAMIC_MARKET_TARGET_REL.name:
        return english_literals_from_workbench_bundle(content, limit=limit)
    return []


def sample_limit_for_path(path: Path) -> int:
    if path.name in {"nls.messages.json", DYNAMIC_MARKET_TARGET_REL.name}:
        return 120
    return 30


def translation_candidates_for_literal(literal: str) -> list[str]:
    candidates: list[str] = []
    for candidate in (literal, json.dumps(literal, ensure_ascii=False)):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    return candidates


def apply_replacements_to_content(content: str, replacements: list[dict[str, Any]]) -> tuple[str, int]:
    out = content
    total_hits = 0
    for repl in replacements:
        hit = out.count(repl["from"])
        if hit <= 0:
            continue
        total_hits += hit
        out = out.replace(repl["from"], repl["to"])
    return out, total_hits


def promote_core_sample_literals_for_path(
    path: Path,
    content: str,
    residual_literals: list[str],
    tracked_hits: dict[str, int],
    translations: dict[str, str],
    core_phrases: set[str],
) -> dict[str, int]:
    promoted_hits: dict[str, int] = {}
    for literal in residual_literals:
        for candidate in translation_candidates_for_literal(literal):
            if candidate in tracked_hits:
                continue
            if candidate not in translations or candidate not in core_phrases:
                continue
            if not is_safe_static_phrase_for_path(path, candidate):
                continue
            count = content.count(candidate)
            if count <= 0:
                continue
            tracked_hits[candidate] = count
            promoted_hits[candidate] = count
    return promoted_hits


def is_dynamic_candidate_literal(literal: str) -> bool:
    text = literal.strip()
    if len(text) < 8 or " " not in text:
        return False
    if text.startswith("$(") or text.endswith(".json"):
        return False
    if "http://" in text or "https://" in text:
        return False
    if text.endswith(", Inc."):
        return False
    if re.search(r"(^|[^A-Za-z])(on[A-Z][A-Za-z0-9]+|[A-Za-z0-9_-]+\.[A-Za-z0-9_.-]+)($|[^A-Za-z])", text):
        return False
    if re.search(r"[/*{}=]", text):
        return False
    words = re.findall(r"[A-Za-z]+", text)
    return len(words) >= 3


def file_fingerprint(ctx: CursorContext) -> str:
    commit_short = ctx.commit[:8] if ctx.commit and ctx.commit != "unknown" else "unknown"
    return f"{ctx.version}_{commit_short}"


def build_agent_menu_contextual_replacements(path: Path, content: str) -> list[dict[str, Any]]:
    if path.name != DYNAMIC_MARKET_TARGET_REL.name:
        return []
    replacements: list[dict[str, Any]] = []
    for rule in AGENT_MENU_CONTEXTUAL_REPLACEMENTS:
        count = content.count(rule["source"])
        if count <= 0:
            continue
        replacements.append(
            {
                "id": rule["id"],
                "from": rule["source"],
                "to": rule["target"],
                "expected_hits": count,
            }
        )
    return replacements


def run_scan(ctx: CursorContext) -> dict[str, Any]:
    ensure_dirs()
    translations = load_custom_phrases()
    core_phrases = set(load_core_phrases())
    tracked_phrases = sorted(translations.keys(), key=len, reverse=True)
    targets = iter_cursor_targets(ctx)

    report_files: list[dict[str, Any]] = []
    total_hits = 0
    distinct_hits: set[str] = set()
    core_detected: set[str] = set()
    residual_literals_total = 0
    dynamic_literals_total = 0
    technical_literals_total = 0
    promoted_phrase_items = 0
    promoted_phrase_hits = 0

    for file_path in targets:
        content = read_text(file_path)
        scan_content = strip_dynamic_market_patch(content) if file_path.name == DYNAMIC_MARKET_TARGET_REL.name else content
        tracked_hits: dict[str, int] = {}
        for phrase in tracked_phrases:
            if not is_safe_static_phrase_for_path(file_path, phrase):
                continue
            count = scan_content.count(phrase)
            if count > 0:
                tracked_hits[phrase] = count
                total_hits += count
                distinct_hits.add(phrase)
                if phrase in core_phrases:
                    core_detected.add(phrase)
        residual_literals = sample_english_literals_for_path(file_path, scan_content, limit=sample_limit_for_path(file_path))
        promoted_hits = promote_core_sample_literals_for_path(
            file_path,
            scan_content,
            residual_literals,
            tracked_hits,
            translations,
            core_phrases,
        )
        for phrase, count in promoted_hits.items():
            total_hits += count
            distinct_hits.add(phrase)
            core_detected.add(phrase)
            promoted_phrase_items += 1
            promoted_phrase_hits += count
        dynamic_literals = [item for item in residual_literals if is_dynamic_candidate_literal(item)]
        technical_literals = [item for item in residual_literals if item not in dynamic_literals]
        residual_literals_total += len(residual_literals)
        dynamic_literals_total += len(dynamic_literals)
        technical_literals_total += len(technical_literals)
        report_files.append(
            {
                "path": str(file_path),
                "sha256": sha256_text(content),
                "bytes": len(content.encode("utf-8", errors="ignore")),
                "tracked_hits": tracked_hits,
                "sample_english_literals": residual_literals,
                "sample_dynamic_literals": dynamic_literals[:15],
                "promoted_core_hits": promoted_hits,
                "sample_technical_literals": technical_literals[:15],
            }
        )

    report = {
        "generated_at": now_iso(),
        "cursor": {
            "app_path": str(ctx.app_path),
            "version": ctx.version,
            "commit": ctx.commit,
            "lang_pack_path": str(ctx.lang_pack_path) if ctx.lang_pack_path else None,
        },
        "summary": {
            "target_files": len(targets),
            "distinct_hit_phrases": len(distinct_hits),
            "total_phrase_hits": total_hits,
            "core_detected": len(core_detected),
            "residual_english_literals": residual_literals_total,
            "static_distinct_hit_phrases": len(distinct_hits),
            "static_total_phrase_hits": total_hits,
            "dynamic_candidate_literals": dynamic_literals_total,
            "promoted_core_phrase_items": promoted_phrase_items,
            "promoted_core_phrase_hits": promoted_phrase_hits,
            "technical_literals": technical_literals_total,
        },
        "files": report_files,
    }
    fp = file_fingerprint(ctx)
    output_path = SCAN_DIR / f"{fp}.json"
    write_json(output_path, report)
    write_json(SCAN_DIR / "latest.json", report)
    write_json(STATE_DIR / "last_scan.json", {"path": str(output_path), "generated_at": report["generated_at"]})
    return report


def load_scan(path: Path | None) -> dict[str, Any]:
    if path:
        return read_json(path)
    latest = SCAN_DIR / "latest.json"
    if not latest.exists():
        raise FileNotFoundError("缺少扫描结果，请先运行 cursor-zh scan")
    return read_json(latest)


def run_build(scan_report: dict[str, Any]) -> dict[str, Any]:
    ensure_dirs()
    translations = load_custom_phrases()
    cursor_app_path_raw = scan_report.get("cursor", {}).get("app_path")
    cursor_app_path = Path(cursor_app_path_raw) if cursor_app_path_raw else None
    files: list[dict[str, Any]] = []
    untranslated: set[str] = set()
    replacement_items = 0
    replacement_hits = 0

    for file_entry in scan_report.get("files", []):
        file_path = Path(file_entry["path"])
        if is_blocked_static_target(file_path):
            continue
        tracked = file_entry.get("tracked_hits", {})
        replacements: list[dict[str, Any]] = []
        contextual_replacements: list[dict[str, Any]] = []
        for src, count in tracked.items():
            if not is_safe_static_phrase_for_path(file_path, src):
                continue
            target = translations.get(src)
            if target:
                replacements.append({"from": src, "to": target, "expected_hits": count})
                replacement_items += 1
                replacement_hits += int(count)
            else:
                untranslated.add(src)
        if replacements:
            replacements.sort(key=lambda item: len(item["from"]), reverse=True)
        if file_path.exists():
            preview_content = read_text(file_path)
            preview_content, _ = apply_replacements_to_content(preview_content, replacements)
            contextual_replacements = build_agent_menu_contextual_replacements(file_path, preview_content)
            if contextual_replacements:
                replacement_items += len(contextual_replacements)
                replacement_hits += sum(int(item["expected_hits"]) for item in contextual_replacements)
        if replacements or contextual_replacements:
            file_record = {
                "path": file_entry["path"],
                "source_sha256": file_entry["sha256"],
                "replacements": replacements,
            }
            if contextual_replacements:
                file_record["contextual_replacements"] = contextual_replacements
            if cursor_app_path:
                rel = relative_target_path(cursor_app_path, file_path)
                if rel:
                    file_record["target_rel_path"] = rel
            files.append(file_record)

    cursor_info = scan_report.get("cursor", {})
    version = cursor_info.get("version", "unknown")
    commit = cursor_info.get("commit", "unknown")
    commit_short = commit[:8] if commit != "unknown" else "unknown"
    manifest = {
        "manifest_version": 1,
        "generated_at": now_iso(),
        "cursor": cursor_info,
        "summary": {
            "files_with_replacements": len(files),
            "replacement_items": replacement_items,
            "replacement_expected_hits": replacement_hits,
            "untranslated_phrases_count": len(untranslated),
        },
        "untranslated_phrases": sorted(untranslated),
        "files": files,
    }
    output = PATCH_MANIFEST_DIR / f"{version}_{commit_short}.json"
    write_json(output, manifest)
    write_json(PATCH_MANIFEST_DIR / "latest.json", manifest)
    write_json(
        STATE_DIR / "last_manifest.json",
        {"path": str(output), "generated_at": manifest["generated_at"], "version": version, "commit": commit},
    )
    return manifest


def load_manifest(path: Path | None) -> dict[str, Any]:
    if path:
        return read_json(path)
    latest = PATCH_MANIFEST_DIR / "latest.json"
    if not latest.exists():
        raise FileNotFoundError("缺少 patch manifest，请先运行 cursor-zh build")
    return read_json(latest)


def collect_qa_issues(
    manifest: dict[str, Any],
    forced_terms: dict[str, str],
    keep_terms: list[str],
    forbidden_terms: list[str],
) -> dict[str, list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    infos: list[dict[str, Any]] = []

    for file_item in manifest.get("files", []):
        path = file_item["path"]
        for repl in file_item.get("replacements", []):
            src = repl["from"]
            dst = repl["to"]
            src_ph = sorted(PH_RE.findall(src))
            dst_ph = sorted(PH_RE.findall(dst))
            if src_ph != dst_ph:
                errors.append(
                    {
                        "type": "placeholder_mismatch",
                        "path": path,
                        "source": src,
                        "target": dst,
                        "source_placeholders": src_ph,
                        "target_placeholders": dst_ph,
                    }
                )

            for forbidden in forbidden_terms:
                if forbidden and forbidden in dst:
                    errors.append(
                        {
                            "type": "forbidden_term",
                            "path": path,
                            "source": src,
                            "target": dst,
                            "forbidden": forbidden,
                        }
                    )

            src_len = max(len(src.strip()), 1)
            ratio = len(dst.strip()) / src_len
            if ratio < 0.35 or ratio > 3.5:
                warnings.append(
                    {
                        "type": "length_ratio_outlier",
                        "path": path,
                        "source": src,
                        "target": dst,
                        "ratio": round(ratio, 3),
                    }
                )

            src_lower = src.lower()
            dst_lower = dst.lower()
            for term in keep_terms:
                term_lower = term.lower()
                term_pattern = re.compile(rf"\b{re.escape(term_lower)}\b")
                if term_pattern.search(src_lower) and not term_pattern.search(dst_lower):
                    errors.append(
                        {
                            "type": "keep_english_term_missing",
                            "path": path,
                            "source": src,
                            "target": dst,
                            "term": term,
                        }
                    )

            for term_en, term_zh in forced_terms.items():
                if term_en.lower() in src_lower and term_zh not in dst:
                    warnings.append(
                        {
                            "type": "forced_term_not_used",
                            "path": path,
                            "source": src,
                            "target": dst,
                            "term_en": term_en,
                            "term_zh": term_zh,
                        }
                    )

    infos.append(
        {
            "type": "qa_stats",
            "replacement_items": manifest.get("summary", {}).get("replacement_items", 0),
            "untranslated_phrases_count": manifest.get("summary", {}).get("untranslated_phrases_count", 0),
        }
    )
    return {"errors": errors, "warnings": warnings, "infos": infos}


def run_qa(manifest: dict[str, Any]) -> dict[str, Any]:
    forced_terms = load_forced_terms()
    keep_terms = load_keep_english_terms()
    forbidden_terms = load_forbidden_terms()
    issues = collect_qa_issues(manifest, forced_terms, keep_terms, forbidden_terms)
    report = {
        "generated_at": now_iso(),
        "manifest_cursor": manifest.get("cursor", {}),
        "summary": {
            "errors": len(issues["errors"]),
            "warnings": len(issues["warnings"]),
            "infos": len(issues["infos"]),
        },
        "issues": issues,
    }
    write_json(QA_DIR / "latest.json", report)
    return report


def safe_backup_path(backup_root: Path, original: Path) -> Path:
    rel = original.as_posix().lstrip("/")
    return backup_root / rel


def record_changed_file(changed_files: list[dict[str, Any]], path: Path, backup_path: Path, hits: int = 1) -> None:
    for item in changed_files:
        if item["path"] == str(path):
            item["hits"] = int(item.get("hits", 0)) + hits
            return
    changed_files.append({"path": str(path), "backup_path": str(backup_path), "hits": hits})


def product_checksum_key_for_path(app_path: Path, path: Path) -> str | None:
    try:
        rel = path.resolve(strict=False).relative_to(app_path.resolve(strict=False))
    except ValueError:
        return None

    rel_posix = rel.as_posix()
    if rel_posix.startswith("out/"):
        return rel_posix[4:]
    if rel_posix.startswith("extensions/") and rel.name == "package.json":
        return rel_posix
    return None


def product_checksum_target_path(app_path: Path, rel: str) -> Path:
    normalized = rel.strip("/")
    if normalized.startswith("extensions/"):
        return app_path / normalized
    return app_path / "out" / normalized


def collect_product_checksum_updates(
    app_path: Path,
    touched_paths: list[Path] | None = None,
    include_all_existing: bool = False,
) -> dict[str, str]:
    product_path = app_path / "product.json"
    if not product_path.exists():
        return {}
    product = read_json(product_path)
    checksums = product.get("checksums")
    if not isinstance(checksums, dict):
        return {}

    touched_resolved: set[str] = set()
    if touched_paths:
        for raw in touched_paths:
            touched_resolved.add(str(raw.resolve(strict=False)))

    candidate_keys: set[str] = set()
    if include_all_existing or not touched_paths:
        candidate_keys.update(rel for rel in checksums.keys() if isinstance(rel, str))
    else:
        for rel in checksums.keys():
            if not isinstance(rel, str):
                continue
            target = product_checksum_target_path(app_path, rel)
            if str(target.resolve(strict=False)) in touched_resolved:
                candidate_keys.add(rel)

    for raw in touched_paths or []:
        key = product_checksum_key_for_path(app_path, raw)
        if key:
            candidate_keys.add(key)

    updates: dict[str, str] = {}
    for rel in sorted(candidate_keys):
        target = product_checksum_target_path(app_path, rel)
        if not target.exists():
            continue
        digest = sha256_file_base64(target)
        if checksums.get(rel) != digest:
            updates[rel] = digest
    return updates


def normalize_dynamic_market_pairs(translations: dict[str, str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for src, dst in translations.items():
        if not isinstance(src, str) or not isinstance(dst, str):
            continue
        source = src.strip()
        target = dst.strip()
        if not source or not target or source == target:
            continue
        pairs.append((source, target))
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return pairs


def build_dynamic_market_patch_block(pairs: list[tuple[str, str]]) -> str:
    serialized = json.dumps(pairs, ensure_ascii=False)
    return "\n".join(
        [
            DYNAMIC_MARKET_MARK_BEGIN,
            ";(()=>{",
            "const MAP_PAIRS=" + serialized + ";",
            "const MARKET_URL_SIGNS=['marketplace.cursorapi.com','/_apis/public/gallery','/marketplace'];",
            "const TARGET_FIELDS=new Set(['description','shortDescription','summary','tagline','title','displayName']);",
            "const replaceText=(value)=>{",
            "  if(typeof value!=='string'||!value){return value;}",
            "  let out=value;",
            "  for(const pair of MAP_PAIRS){",
            "    const src=pair[0], dst=pair[1];",
            "    if(out===src){return dst;}",
            "    if(src&&out.includes(src)){out=out.split(src).join(dst);}",
            "  }",
            "  return out;",
            "};",
            "const translate=(node,depth=0,allowString=true)=>{",
            "  if(depth>10||node===null||node===undefined){return node;}",
            "  if(typeof node==='string'){return allowString?replaceText(node):node;}",
            "  if(Array.isArray(node)){",
            "    let changed=false;",
            "    const next=node.map((item)=>{const patched=translate(item,depth+1,allowString);if(patched!==item){changed=true;}return patched;});",
            "    return changed?next:node;",
            "  }",
            "  if(typeof node==='object'){",
            "    let changed=false;",
            "    const next={};",
            "    for(const entry of Object.entries(node)){",
            "      const key=entry[0], value=entry[1];",
            "      let patched=value;",
            "      if(typeof value==='string'&&TARGET_FIELDS.has(key)){patched=replaceText(value);}else{patched=translate(value,depth+1,false);}",
            "      if(patched!==value){changed=true;}",
            "      next[key]=patched;",
            "    }",
            "    return changed?next:node;",
            "  }",
            "  return node;",
            "};",
            "const shouldPatchUrl=(url)=>{",
            "  if(typeof url!=='string'||!url){return false;}",
            "  const lower=url.toLowerCase();",
            "  return MARKET_URL_SIGNS.some((token)=>lower.includes(token));",
            "};",
            "if(typeof globalThis.fetch==='function'){",
            "  const origFetch=globalThis.fetch.bind(globalThis);",
            "  globalThis.fetch=async (...args)=>{",
            "    const response=await origFetch(...args);",
            "    try{",
            "      const req=args[0];",
            "      const url=typeof req==='string'?req:(req&&typeof req.url==='string'?req.url:'');",
            "      if(!shouldPatchUrl(url)){return response;}",
            "      if(!response||typeof response.json!=='function'){return response;}",
            "      const origJson=response.json.bind(response);",
            "      let state=0;",
            "      let cached;",
            "      response.json=async ()=>{",
            "        if(state===1){return cached;}",
            "        try{",
            "          const payload=await origJson();",
            "          cached=translate(payload,0,true);",
            "          state=1;",
            "          return cached;",
            "        }catch(err){",
            "          state=2;",
            "          throw err;",
            "        }",
            "      };",
            "      return response;",
            "    }catch(_err){",
            "      return response;",
            "    }",
            "  };",
            "}",
            "if(typeof document!=='undefined'&&document.body&&typeof MutationObserver==='function'&&typeof NodeFilter!=='undefined'){",
            "  const patchNode=(textNode)=>{",
            "    const value=textNode&&textNode.nodeValue;",
            "    if(!value){return;}",
            "    const next=replaceText(value);",
            "    if(next!==value){textNode.nodeValue=next;}",
            "  };",
            "  const patchRoot=(root)=>{",
            "    if(!root){return;}",
            "    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);",
            "    let current=walker.nextNode();",
            "    let guard=0;",
            "    while(current&&guard<2000){patchNode(current);current=walker.nextNode();guard+=1;}",
            "  };",
            "  patchRoot(document.body);",
            "  const observer=new MutationObserver((mutations)=>{",
            "    for(const mutation of mutations){",
            "      if(mutation.type==='characterData'){patchNode(mutation.target);}",
            "      for(const node of mutation.addedNodes||[]){",
            "        if(node&&node.nodeType===3){patchNode(node);}",
            "        else if(node&&(node.nodeType===1||node.nodeType===11)){patchRoot(node);}",
            "      }",
            "    }",
            "  });",
            "  observer.observe(document.body,{childList:true,subtree:true,characterData:true});",
            "}",
            "})();",
            DYNAMIC_MARKET_MARK_END,
        ]
    )


def disable_integrity_service(content: str) -> tuple[str, bool]:
    if INTEGRITY_SERVICE_PATCHED in content:
        return content, False
    if INTEGRITY_SERVICE_ORIGINAL not in content:
        return content, False
    return content.replace(INTEGRITY_SERVICE_ORIGINAL, INTEGRITY_SERVICE_PATCHED, 1), True


def has_dynamic_market_patch(content: str) -> bool:
    return DYNAMIC_MARKET_MARK_BEGIN in content and DYNAMIC_MARKET_MARK_END in content


def strip_dynamic_market_patch(content: str) -> str:
    begin = content.find(DYNAMIC_MARKET_MARK_BEGIN)
    end = content.find(DYNAMIC_MARKET_MARK_END)
    if begin < 0 or end < begin:
        return content
    end_pos = end + len(DYNAMIC_MARKET_MARK_END)
    if end_pos < len(content) and content[end_pos : end_pos + 1] == "\n":
        end_pos += 1
    return f"{content[:begin]}{content[end_pos:]}"


def upsert_dynamic_market_patch(content: str, patch_block: str) -> tuple[str, bool]:
    begin = content.find(DYNAMIC_MARKET_MARK_BEGIN)
    end = content.find(DYNAMIC_MARKET_MARK_END)
    if begin >= 0 and end >= begin:
        end_pos = end + len(DYNAMIC_MARKET_MARK_END)
        if end_pos < len(content) and content[end_pos : end_pos + 1] == "\n":
            end_pos += 1
        next_content = f"{content[:begin]}{patch_block}\n{content[end_pos:]}"
        return next_content, next_content != content
    suffix = "" if content.endswith("\n") else "\n"
    next_content = f"{content}{suffix}{patch_block}\n"
    return next_content, True


def dynamic_market_anchor_ok(content: str) -> bool:
    return "fetch(" in content


def resolve_manifest_app_path(manifest: dict[str, Any], cursor_app_override: Path | None = None) -> Path | None:
    if cursor_app_override:
        return cursor_app_override
    app_path = manifest.get("cursor", {}).get("app_path")
    return Path(app_path) if app_path else None


def resolve_manifest_file_path(
    manifest: dict[str, Any],
    file_item: dict[str, Any],
    cursor_app_override: Path | None = None,
) -> Path:
    app_path = resolve_manifest_app_path(manifest, cursor_app_override)
    target_rel = file_item.get("target_rel_path")
    if app_path and target_rel:
        return app_path / Path(target_rel)

    path_raw = file_item.get("path")
    if not path_raw:
        raise FileNotFoundError(f"manifest 缺少 path: {file_item}")

    path = Path(path_raw)
    if cursor_app_override:
        manifest_app_path = resolve_manifest_app_path(manifest)
        if manifest_app_path:
            rel = relative_target_path(manifest_app_path, path)
            if rel:
                return cursor_app_override / Path(rel)
    return path


def build_portable_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    portable = json.loads(json.dumps(manifest))
    app_path = resolve_manifest_app_path(manifest)
    cursor = dict(portable.get("cursor", {}))
    cursor["app_path"] = None
    portable["cursor"] = cursor
    portable["portable"] = True

    normalized_files: list[dict[str, Any]] = []
    for file_item in portable.get("files", []):
        item = dict(file_item)
        target_rel = item.get("target_rel_path")
        if not target_rel and app_path and item.get("path"):
            target_rel = relative_target_path(app_path, Path(item["path"]))
        if target_rel:
            item["target_rel_path"] = target_rel
            item["path"] = target_rel
        normalized_files.append(item)
    portable["files"] = normalized_files
    return portable


def build_local_bundle_install_script(enable_dynamic_market: bool) -> str:
    dynamic_literal = "True" if enable_dynamic_market else "False"
    return "\n".join(
        [
            "#!/bin/zsh",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'TARGET_APP="${1:-/Applications/Cursor.app/Contents/Resources/app}"',
            'MANIFEST_PATH="$SCRIPT_DIR/payload/patch_manifest.json"',
            'STATE_PATH="$SCRIPT_DIR/payload/last_apply.json"',
            'export TARGET_APP MANIFEST_PATH STATE_PATH',
            "python3 - <<'PY'",
            "import os",
            "from pathlib import Path",
            "from cursor_zh.cli import apply_manifest, read_json, write_json",
            f"enable_dynamic_market = {dynamic_literal}",
            "target_app = Path(os.environ['TARGET_APP'])",
            "manifest_path = Path(os.environ['MANIFEST_PATH'])",
            "state_path = Path(os.environ['STATE_PATH'])",
            "manifest = read_json(manifest_path)",
            "result = apply_manifest(",
            "    manifest,",
            "    backup_root=state_path.parent / 'backups',",
            "    force=False,",
            "    enable_dynamic_market=enable_dynamic_market,",
            "    cursor_app_override=target_app,",
            ")",
            "write_json(state_path, result)",
            "print(f'已应用到: {target_app}')",
            "PY",
            "",
        ]
    )


def build_local_bundle_rollback_script() -> str:
    return "\n".join(
        [
            "#!/bin/zsh",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'STATE_PATH="$SCRIPT_DIR/payload/last_apply.json"',
            'export STATE_PATH',
            "python3 - <<'PY'",
            "import os",
            "from pathlib import Path",
            "from cursor_zh.cli import read_json, run_rollback",
            "state_path = Path(os.environ['STATE_PATH'])",
            "if not state_path.exists():",
            "    raise SystemExit('未找到 payload/last_apply.json，请先执行安装脚本。')",
            "result = run_rollback(read_json(state_path))",
            "print(f\"已恢复 {result['restored_files_count']} 个文件。\")",
            "PY",
            "",
        ]
    )


def run_export_local_bundle(
    manifest: dict[str, Any],
    output_dir: Path,
    enable_dynamic_market: bool = False,
) -> dict[str, Any]:
    ensure_dirs()
    output_dir.mkdir(parents=True, exist_ok=True)
    payload_dir = output_dir / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)

    portable_manifest = build_portable_manifest(manifest)
    portable_manifest["bundle_options"] = {
        "enable_dynamic_market": enable_dynamic_market,
    }
    write_json(payload_dir / "patch_manifest.json", portable_manifest)
    write_text(output_dir / "install-local-patch.command", build_local_bundle_install_script(enable_dynamic_market))
    write_text(output_dir / "rollback-local-patch.command", build_local_bundle_rollback_script())

    for script_path in (
        output_dir / "install-local-patch.command",
        output_dir / "rollback-local-patch.command",
    ):
        current_mode = script_path.stat().st_mode
        script_path.chmod(current_mode | 0o111)

    archive_path = output_dir.with_suffix(".zip")
    if archive_path.exists():
        archive_path.unlink()
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(output_dir.rglob("*")):
            if path.is_dir():
                continue
            zf.write(path, path.relative_to(output_dir))

    report = {
        "generated_at": now_iso(),
        "output_dir": str(output_dir),
        "archive_path": str(archive_path),
        "portable_manifest_path": str(payload_dir / "patch_manifest.json"),
        "enable_dynamic_market": enable_dynamic_market,
    }
    return report


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        len(data).to_bytes(4, "big")
        + tag
        + data
        + (zlib.crc32(tag + data) & 0xFFFFFFFF).to_bytes(4, "big")
    )


def write_png_rgba(path: Path, width: int, height: int, rows: list[bytearray]) -> None:
    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    ihdr = (
        width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + bytes([8, 6, 0, 0, 0])
    )
    png = b"\x89PNG\r\n\x1a\n"
    png += _png_chunk(b"IHDR", ihdr)
    png += _png_chunk(b"IDAT", zlib.compress(raw, level=9))
    png += _png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def write_store_extension_icon(path: Path, size: int = 128) -> None:
    rows = [bytearray(size * 4) for _ in range(size)]

    def set_px(x: int, y: int, color: tuple[int, int, int, int]) -> None:
        if 0 <= x < size and 0 <= y < size:
            i = x * 4
            rows[y][i:i + 4] = bytes(color)

    def fill_rect(x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int, int]) -> None:
        for y in range(max(0, y0), min(size, y1)):
            row = rows[y]
            for x in range(max(0, x0), min(size, x1)):
                i = x * 4
                row[i:i + 4] = bytes(color)

    def fill_round_rect(x0: int, y0: int, x1: int, y1: int, radius: int, color: tuple[int, int, int, int]) -> None:
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                corner_dx = 0
                corner_dy = 0
                if x < x0 + radius:
                    corner_dx = x0 + radius - x - 1
                elif x >= x1 - radius:
                    corner_dx = x - (x1 - radius)
                if y < y0 + radius:
                    corner_dy = y0 + radius - y - 1
                elif y >= y1 - radius:
                    corner_dy = y - (y1 - radius)
                if corner_dx * corner_dx + corner_dy * corner_dy <= radius * radius:
                    set_px(x, y, color)

    def fill_circle(cx: int, cy: int, radius: int, color: tuple[int, int, int, int]) -> None:
        r2 = radius * radius
        for y in range(max(0, cy - radius), min(size, cy + radius + 1)):
            dy = y - cy
            for x in range(max(0, cx - radius), min(size, cx + radius + 1)):
                dx = x - cx
                if dx * dx + dy * dy <= r2:
                    set_px(x, y, color)

    def draw_line(x0: int, y0: int, x1: int, y1: int, thickness: int, color: tuple[int, int, int, int]) -> None:
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        half = max(1, thickness // 2)
        for step in range(steps + 1):
            t = step / steps
            x = round(x0 + dx * t)
            y = round(y0 + dy * t)
            fill_rect(x - half, y - half, x + half + 1, y + half + 1, color)

    navy = (11, 24, 54, 255)
    indigo = (23, 43, 92, 255)
    cyan = (86, 214, 226, 255)
    cream = (248, 244, 232, 255)
    coral = (255, 132, 92, 255)
    deep = (20, 36, 77, 255)

    fill_rect(0, 0, size, size, (0, 0, 0, 0))
    fill_round_rect(8, 8, size - 8, size - 8, 24, navy)
    fill_round_rect(14, 14, size - 14, size - 14, 20, indigo)
    fill_circle(size // 2, size // 2, 34, cream)
    fill_circle(size // 2, size // 2, 28, navy)
    fill_circle(size // 2, size // 2, 22, cyan)

    fill_round_rect(22, 28, size - 22, size - 28, 18, cream)
    fill_round_rect(28, 34, size - 28, size - 34, 14, deep)
    fill_round_rect(34, 40, size // 2, size - 40, 10, cream)
    fill_round_rect(size // 2, 40, size - 34, size - 40, 10, coral)

    # Stylized "A"
    draw_line(42, 84, 50, 50, 6, deep)
    draw_line(50, 50, 58, 84, 6, deep)
    fill_rect(46, 68, 55, 73, deep)

    # Stylized Chinese glyph strokes
    draw_line(76, 52, 86, 68, 6, cream)
    draw_line(96, 52, 86, 68, 6, cream)
    draw_line(86, 68, 86, 82, 6, cream)
    draw_line(74, 84, 98, 84, 6, cream)
    draw_line(78, 70, 74, 84, 6, cream)
    draw_line(94, 70, 98, 84, 6, cream)

    write_png_rgba(path, size, size, rows)


def build_store_extension_license() -> str:
    return "\n".join(
        [
            "MIT License",
            "",
            "Copyright (c) 2026 Beta-cursor 汉化 contributors",
            "",
            "Permission is hereby granted, free of charge, to any person obtaining a copy",
            "of this software and associated documentation files (the \"Software\"), to deal",
            "in the Software without restriction, including without limitation the rights",
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell",
            "copies of the Software, and to permit persons to whom the Software is",
            "furnished to do so, subject to the following conditions:",
            "",
            "The above copyright notice and this permission notice shall be included in all",
            "copies or substantial portions of the Software.",
            "",
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR",
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,",
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE",
            "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER",
            "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,",
            "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE",
            "SOFTWARE.",
            "",
        ]
    )


def build_store_extension_gitignore() -> str:
    return "\n".join(
        [
            "node_modules/",
            ".npm-cache/",
            "*.vsix",
            "*.zip",
            "",
        ]
    )


def build_store_extension_package_script() -> str:
    return "\n".join(
        [
            "#!/bin/zsh",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'cd "$ROOT_DIR"',
            'export npm_config_cache="$ROOT_DIR/.npm-cache"',
            "npx -y @vscode/vsce package --allow-missing-repository",
            "",
        ]
    )


def build_store_extension_publish_script() -> str:
    return "\n".join(
        [
            "#!/bin/zsh",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'cd "$ROOT_DIR"',
            'export npm_config_cache="$ROOT_DIR/.npm-cache"',
            'TOKEN="${OPEN_VSX_TOKEN:-}"',
            'if [[ -z "$TOKEN" ]]; then',
            '  echo "缺少 OPEN_VSX_TOKEN 环境变量" >&2',
            "  exit 1",
            "fi",
            'VSIX="$(ls -t ./*.vsix 2>/dev/null | head -n 1 || true)"',
            'if [[ -z "$VSIX" ]]; then',
            '  npx -y @vscode/vsce package',
            '  VSIX="$(ls -t ./*.vsix | head -n 1)"',
            "fi",
            'npx -y ovsx publish "$VSIX" -p "$TOKEN"',
            "",
        ]
    )


def write_store_extension_assets(output_dir: Path) -> None:
    media_dir = output_dir / "media"
    scripts_dir = output_dir / "scripts"
    media_dir.mkdir(parents=True, exist_ok=True)
    scripts_dir.mkdir(parents=True, exist_ok=True)

    write_store_extension_icon(media_dir / "icon.png")
    write_text(output_dir / "LICENSE", build_store_extension_license())
    write_text(output_dir / ".gitignore", build_store_extension_gitignore())
    write_text(scripts_dir / "package-openvsx.sh", build_store_extension_package_script())
    write_text(scripts_dir / "publish-openvsx.sh", build_store_extension_publish_script())
    vscodeignore = output_dir / ".vscodeignore"
    if vscodeignore.exists():
        vscodeignore.unlink()

    for script_path in (
        scripts_dir / "package-openvsx.sh",
        scripts_dir / "publish-openvsx.sh",
    ):
        current_mode = script_path.stat().st_mode
        script_path.chmod(current_mode | 0o111)


def resolve_workbench_target_path(
    manifest: dict[str, Any],
    cursor_app_override: Path | None = None,
) -> Path | None:
    for file_item in manifest.get("files", []):
        maybe = resolve_manifest_file_path(manifest, file_item, cursor_app_override)
        if maybe.name == DYNAMIC_MARKET_TARGET_REL.name:
            return maybe
    app_path = resolve_manifest_app_path(manifest, cursor_app_override)
    if not app_path:
        return None
    return app_path / DYNAMIC_MARKET_TARGET_REL


def inspect_dynamic_market_target(
    manifest: dict[str, Any],
    cursor_app_override: Path | None = None,
) -> dict[str, Any]:
    target = resolve_workbench_target_path(manifest, cursor_app_override)
    if not target:
        return {
            "enabled": False,
            "target_path": None,
            "applied": False,
            "reason": "missing_target",
            "anchor_ok": False,
            "marker_present": False,
            "phrase_pairs": 0,
        }
    if not target.exists():
        return {
            "enabled": False,
            "target_path": str(target),
            "applied": False,
            "reason": "missing_file",
            "anchor_ok": False,
            "marker_present": False,
            "phrase_pairs": 0,
        }
    content = read_text(target)
    marker_present = has_dynamic_market_patch(content)
    anchor_ok = dynamic_market_anchor_ok(content)
    return {
        "enabled": False,
        "target_path": str(target),
        "applied": False,
        "reason": "ready",
        "anchor_ok": anchor_ok,
        "marker_present": marker_present,
        "phrase_pairs": len(normalize_dynamic_market_pairs(load_dynamic_market_phrases())),
    }


def inspect_integrity_patch_target(
    manifest: dict[str, Any],
    cursor_app_override: Path | None = None,
) -> dict[str, Any]:
    target = resolve_workbench_target_path(manifest, cursor_app_override)
    if not target:
        return {
            "target_path": None,
            "applied": False,
            "reason": "missing_target",
        }
    if not target.exists():
        return {
            "target_path": str(target),
            "applied": False,
            "reason": "missing_file",
        }

    content = read_text(target)
    if INTEGRITY_SERVICE_PATCHED in content:
        reason = "already_patched"
    elif INTEGRITY_SERVICE_ORIGINAL in content:
        reason = "would_apply"
    else:
        reason = "not_found"

    return {
        "target_path": str(target),
        "applied": False,
        "reason": reason,
    }


def dry_run_apply(
    manifest: dict[str, Any],
    force: bool,
    enable_dynamic_market: bool = False,
    cursor_app_override: Path | None = None,
) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    checksum_mismatch: list[str] = []
    missing_files: list[str] = []
    total_replacements = 0

    for file_item in manifest.get("files", []):
        path = resolve_manifest_file_path(manifest, file_item, cursor_app_override)
        if not path.exists():
            missing_files.append(str(path))
            continue
        content = read_text(path)
        actual_sha = sha256_text(content)
        expected_sha = file_item["source_sha256"]
        if not force and actual_sha != expected_sha:
            checksum_mismatch.append(str(path))
        file_counts = []
        static_preview, _ = apply_replacements_to_content(content, file_item.get("replacements", []))
        for repl in file_item.get("replacements", []):
            hit = content.count(repl["from"])
            if hit > 0:
                total_replacements += hit
            file_counts.append(
                {
                    "from": repl["from"],
                    "to": repl["to"],
                    "expected_hits": repl["expected_hits"],
                    "actual_hits": hit,
                }
            )
        contextual_counts = []
        for repl in file_item.get("contextual_replacements", []):
            hit = static_preview.count(repl["from"])
            if hit > 0:
                total_replacements += hit
            contextual_counts.append(
                {
                    "id": repl.get("id"),
                    "from": repl["from"],
                    "to": repl["to"],
                    "expected_hits": repl["expected_hits"],
                    "actual_hits": hit,
                }
            )
        details.append(
            {
                "path": str(path),
                "replacement_counts": file_counts,
                "contextual_replacement_counts": contextual_counts,
            }
        )

    dynamic_status = inspect_dynamic_market_target(manifest, cursor_app_override)
    dynamic_status["enabled"] = enable_dynamic_market
    if enable_dynamic_market:
        if dynamic_status["marker_present"]:
            dynamic_status["reason"] = "already_patched"
        elif not dynamic_status["anchor_ok"]:
            dynamic_status["reason"] = "anchor_missing"
        elif dynamic_status["phrase_pairs"] <= 0:
            dynamic_status["reason"] = "no_translations"
        else:
            dynamic_status["reason"] = "would_apply"
    else:
        dynamic_status["reason"] = "disabled"

    integrity_status = inspect_integrity_patch_target(manifest, cursor_app_override)

    return {
        "generated_at": now_iso(),
        "summary": {
            "missing_files": len(missing_files),
            "checksum_mismatch": len(checksum_mismatch),
            "total_replacements_preview": total_replacements,
            "dynamic_market_patch": dynamic_status["reason"],
            "integrity_patch": integrity_status["reason"],
        },
        "missing_files": missing_files,
        "checksum_mismatch": checksum_mismatch,
        "details": details,
        "dynamic_market_patch": dynamic_status,
        "integrity_patch": integrity_status,
    }


def apply_manifest(
    manifest: dict[str, Any],
    backup_root: Path,
    force: bool,
    enable_dynamic_market: bool = False,
    cursor_app_override: Path | None = None,
) -> dict[str, Any]:
    preview = dry_run_apply(
        manifest,
        force=force,
        enable_dynamic_market=enable_dynamic_market,
        cursor_app_override=cursor_app_override,
    )
    if preview["summary"]["missing_files"] > 0:
        raise RuntimeError("存在缺失文件，无法应用补丁")
    if preview["summary"]["checksum_mismatch"] > 0 and not force:
        raise RuntimeError("存在源文件校验不一致，请先运行 upgrade 或使用 --force")

    changed_files: list[dict[str, Any]] = []
    backup_root.mkdir(parents=True, exist_ok=True)
    app_path = resolve_manifest_app_path(manifest, cursor_app_override)

    try:
        for file_item in manifest.get("files", []):
            path = resolve_manifest_file_path(manifest, file_item, cursor_app_override)
            if is_blocked_static_target(path):
                continue
            content = read_text(path)
            backup_path = safe_backup_path(backup_root, path)
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            write_text(backup_path, content)

            content, replacement_hits = apply_replacements_to_content(content, file_item.get("replacements", []))
            content, contextual_hits = apply_replacements_to_content(
                content, file_item.get("contextual_replacements", [])
            )
            total_hits = replacement_hits + contextual_hits
            if total_hits > 0:
                write_text(path, content)
                record_changed_file(changed_files, path, backup_path, total_hits)

        dynamic_status = {
            "enabled": enable_dynamic_market,
            "target_path": None,
            "applied": False,
            "reason": "disabled",
            "anchor_ok": False,
            "marker_present": False,
            "phrase_pairs": 0,
        }
        integrity_status = preview.get(
            "integrity_patch",
            {
                "target_path": None,
                "applied": False,
                "reason": "missing_target",
            },
        )
        workbench_target = resolve_workbench_target_path(manifest, cursor_app_override)
        if enable_dynamic_market:
            dynamic_status = inspect_dynamic_market_target(manifest, cursor_app_override)
            dynamic_status["enabled"] = True
        else:
            dynamic_status = preview.get(
                "dynamic_market_patch",
                {
                    "enabled": False,
                    "target_path": None,
                    "applied": False,
                    "reason": "disabled",
                    "anchor_ok": False,
                    "marker_present": False,
                    "phrase_pairs": 0,
                },
            )

        if workbench_target and workbench_target.exists():
            content = read_text(workbench_target)
            next_content = content
            workbench_changed = False

            if enable_dynamic_market:
                dynamic_status["target_path"] = str(workbench_target)
                if dynamic_status.get("phrase_pairs", 0) <= 0:
                    dynamic_status["reason"] = "no_translations"
                elif not dynamic_status.get("anchor_ok") and not dynamic_status.get("marker_present"):
                    dynamic_status["reason"] = "anchor_missing"
                else:
                    patch_block = build_dynamic_market_patch_block(
                        normalize_dynamic_market_pairs(load_dynamic_market_phrases())
                    )
                    next_content, dynamic_changed = upsert_dynamic_market_patch(next_content, patch_block)
                    if dynamic_changed:
                        workbench_changed = True
                        dynamic_status["applied"] = True
                        dynamic_status["reason"] = (
                            "updated" if dynamic_status.get("marker_present") else "applied"
                        )
                    else:
                        dynamic_status["reason"] = "already_patched"

            next_content, integrity_changed = disable_integrity_service(next_content)
            if integrity_changed:
                workbench_changed = True
                integrity_status = {
                    "target_path": str(workbench_target),
                    "applied": True,
                    "reason": "applied",
                }
            elif INTEGRITY_SERVICE_PATCHED in next_content:
                integrity_status = {
                    "target_path": str(workbench_target),
                    "applied": False,
                    "reason": "already_patched",
                }
            else:
                integrity_status = {
                    "target_path": str(workbench_target),
                    "applied": False,
                    "reason": "not_found",
                }

            if workbench_changed:
                backup_path = safe_backup_path(backup_root, workbench_target)
                if not backup_path.exists():
                    backup_path.parent.mkdir(parents=True, exist_ok=True)
                    write_text(backup_path, content)
                write_text(workbench_target, next_content)
                record_changed_file(changed_files, workbench_target, backup_path, 1)

        checksum_status = {
            "enabled": app_path is not None,
            "updated": 0,
            "updated_keys": [],
            "reason": "disabled",
        }
        if app_path:
            # Always resync the full checksum table so pre-existing mismatches
            # don't keep triggering the "corrupt installation" warning.
            updates = collect_product_checksum_updates(
                app_path,
                touched_paths=[Path(item["path"]) for item in changed_files],
                include_all_existing=True,
            )
            if updates:
                product_path = app_path / "product.json"
                product_backup = safe_backup_path(backup_root, product_path)
                if not product_backup.exists():
                    product_backup.parent.mkdir(parents=True, exist_ok=True)
                    write_text(product_backup, read_text(product_path))
                record_changed_file(changed_files, product_path, product_backup, len(updates))

                product = read_json(product_path)
                checksums = product.get("checksums")
                if isinstance(checksums, dict):
                    for key, value in updates.items():
                        checksums[key] = value
                    product["checksums"] = checksums
                    write_json(product_path, product)
                    checksum_status["reason"] = "updated"
                    checksum_status["updated"] = len(updates)
                    checksum_status["updated_keys"] = sorted(updates.keys())
                else:
                    checksum_status["reason"] = "missing_checksums"
            else:
                checksum_status["reason"] = "up_to_date"
        else:
            checksum_status["reason"] = "missing_app_path"
    except Exception:
        for item in changed_files:
            origin = Path(item["path"])
            backup = Path(item["backup_path"])
            if backup.exists():
                write_text(origin, read_text(backup))
        raise

    result = {
        "generated_at": now_iso(),
        "backup_root": str(backup_root),
        "changed_files": changed_files,
        "changed_files_count": len(changed_files),
        "dynamic_market_patch": dynamic_status,
        "integrity_patch": integrity_status,
        "checksum_sync": checksum_status,
    }
    write_json(STATE_DIR / "last_apply.json", result)
    return result


def run_verify(manifest: dict[str, Any], threshold: float) -> dict[str, Any]:
    core_phrases = set(load_core_phrases())
    forbidden_terms = load_forbidden_terms()
    keep_terms = [t.lower() for t in load_keep_english_terms()]

    phrase_status: dict[str, dict[str, Any]] = {}
    forbidden_hits: list[dict[str, Any]] = []

    for file_item in manifest.get("files", []):
        path = Path(file_item["path"])
        if not path.exists():
            continue
        content = read_text(path)
        verify_content = strip_dynamic_market_patch(content) if path.name == DYNAMIC_MARKET_TARGET_REL.name else content
        for term in forbidden_terms:
            if term and term in verify_content:
                forbidden_hits.append({"path": str(path), "term": term})

        for repl in file_item.get("replacements", []):
            src = repl["from"]
            dst = repl["to"]
            src_count = verify_content.count(src)
            dst_count = verify_content.count(dst)
            slot = phrase_status.setdefault(
                src,
                {
                    "source": src,
                    "target": dst,
                    "remaining_english": 0,
                    "translated_hits": 0,
                    "is_core": src in core_phrases,
                    "is_exempt_keep_english": False,
                },
            )
            slot["remaining_english"] += src_count
            slot["translated_hits"] += dst_count
            src_norm = src.strip().strip('"').lower()
            dst_norm = dst.strip().strip('"').lower()
            if src_norm == dst_norm:
                slot["is_exempt_keep_english"] = True
            elif not CJK_RE.search(dst):
                for term in keep_terms:
                    if re.search(rf"\b{re.escape(term)}\b", src_norm):
                        slot["is_exempt_keep_english"] = True
                        break

    core_items = [
        item
        for item in phrase_status.values()
        if item["is_core"] and not item.get("is_exempt_keep_english", False)
    ]
    translated_core = [
        item for item in core_items if item["remaining_english"] == 0 and item["translated_hits"] > 0
    ]
    residual_core = [item for item in core_items if item not in translated_core]

    total_core = len(core_items)
    coverage = 100.0 if total_core == 0 else (len(translated_core) / total_core) * 100.0
    pass_threshold = coverage >= threshold and len(forbidden_hits) == 0

    report = {
        "generated_at": now_iso(),
        "summary": {
            "core_total": total_core,
            "core_translated": len(translated_core),
            "coverage_percent": round(coverage, 2),
            "threshold_percent": threshold,
            "forbidden_hits": len(forbidden_hits),
            "pass": pass_threshold,
        },
        "residual_core": sorted(residual_core, key=lambda item: item["remaining_english"], reverse=True),
        "forbidden_hits": forbidden_hits,
    }
    write_json(COVERAGE_DIR / "latest.json", report)
    write_text(
        COVERAGE_DIR / "latest.md",
        "\n".join(
            [
                f"# 覆盖率报告",
                f"- 生成时间: {report['generated_at']}",
                f"- 核心短语总数: {report['summary']['core_total']}",
                f"- 已翻译核心短语: {report['summary']['core_translated']}",
                f"- 覆盖率: {report['summary']['coverage_percent']}%",
                f"- 验收阈值: {report['summary']['threshold_percent']}%",
                f"- 禁用词命中: {report['summary']['forbidden_hits']}",
                f"- 结论: {'通过' if report['summary']['pass'] else '未通过'}",
            ]
        )
        + "\n",
    )
    return report


def run_rollback(last_apply: dict[str, Any]) -> dict[str, Any]:
    restored = []
    for item in last_apply.get("changed_files", []):
        target = Path(item["path"])
        backup = Path(item["backup_path"])
        if backup.exists():
            write_text(target, read_text(backup))
            restored.append(str(target))
    result = {
        "generated_at": now_iso(),
        "restored_files_count": len(restored),
        "restored_files": restored,
    }
    write_json(STATE_DIR / "last_rollback.json", result)
    return result


def run_upgrade(ctx: CursorContext, threshold: float) -> dict[str, Any]:
    prev_scan_path = STATE_DIR / "last_scan.json"
    prev_scan = None
    if prev_scan_path.exists():
        meta = read_json(prev_scan_path)
        path = Path(meta.get("path", ""))
        if path.exists():
            prev_scan = read_json(path)

    new_scan = run_scan(ctx)
    manifest = run_build(new_scan)
    qa_report = run_qa(manifest)
    verify_report = run_verify(manifest, threshold=threshold)
    dynamic_target = inspect_dynamic_market_target(manifest)

    old_phrases = set()
    if prev_scan:
        for file_item in prev_scan.get("files", []):
            old_phrases.update(file_item.get("tracked_hits", {}).keys())
    new_phrases = set()
    for file_item in new_scan.get("files", []):
        new_phrases.update(file_item.get("tracked_hits", {}).keys())

    added = sorted(new_phrases - old_phrases)
    removed = sorted(old_phrases - new_phrases)

    manual_review_required = (
        qa_report["summary"]["errors"] > 0
        or manifest["summary"]["untranslated_phrases_count"] > 0
        or verify_report["summary"]["coverage_percent"] < threshold
        or not dynamic_target.get("anchor_ok", False)
    )
    report = {
        "generated_at": now_iso(),
        "cursor": {"version": ctx.version, "commit": ctx.commit},
        "diff": {"added_phrases": added, "removed_phrases": removed},
        "qa_summary": qa_report["summary"],
        "verify_summary": verify_report["summary"],
        "dynamic_market_target": dynamic_target,
        "manual_review_required": manual_review_required,
    }
    write_json(UPGRADE_DIR / "latest.json", report)
    return report


def build_local_bundle_name(manifest: dict[str, Any]) -> str:
    cursor = manifest.get("cursor", {})
    version = str(cursor.get("version", "unknown")).strip() or "unknown"
    commit = str(cursor.get("commit", "unknown")).strip() or "unknown"
    commit_short = commit[:8] if commit != "unknown" else "unknown"
    return f"Beta-Cursor-全面汉化-{version}-{commit_short}"


def build_local_bundle_readme(bundle_name: str, enable_dynamic_market: bool) -> str:
    dynamic_line_zh = (
        "- 安装时默认启用插件市场动态简介补丁。"
        if enable_dynamic_market
        else "- 安装时默认不启用插件市场动态简介补丁。"
    )
    dynamic_line_en = (
        "- The installer enables the dynamic marketplace translation patch by default."
        if enable_dynamic_market
        else "- The installer does not enable the dynamic marketplace translation patch by default."
    )
    return "\n".join(
        [
            f"# {bundle_name}",
            "",
            "这是一个可在另一台电脑上复现的 Cursor 汉化本地补丁包，包含 macOS 与 Windows 启动器。",
            "",
            "## 中文说明",
            "",
            "### 安装",
            "",
            "- 把整个目录拷到目标电脑，不要只拷单个脚本文件。",
            "- macOS：推荐先把目录移到 `~/work`、`~/Applications` 或其他非“桌面/下载/文稿”位置，再进入 `macOS/` 运行 `安装.command`，首次成功率更高。",
            "- Windows：进入 `Windows/`，双击 `Windows/安装.bat`。",
            "- 如需手动指定 Cursor 路径，可按下面方式运行：",
            "",
            "```bash",
            "./macOS/安装.command /Applications/Cursor.app",
            "```",
            "",
            "```bat",
            "Windows\\安装.bat \"C:\\Users\\<You>\\AppData\\Local\\Programs\\Cursor\\resources\\app\"",
            "```",
            "",
            "### 回滚",
            "",
            "- macOS：进入 `macOS/`，双击 `macOS/回滚.command`。",
            "- Windows：进入 `Windows/`，双击 `Windows/回滚.bat`。",
            "- 回滚会恢复本次安装前备份的原文件，不会重装整个 Cursor。",
            "",
            "### 常见问题",
            "",
            "- 双击打不开：macOS 请右键后选择“打开”；Windows 请右键“以管理员身份运行”或在终端里执行。",
            "- macOS 提示“已损坏”或“无法验证开发者”：这通常是 Gatekeeper 对未签名脚本的拦截，并不一定真损坏。先在终端执行 `xattr -dr com.apple.quarantine \"<解压后的补丁目录>\"`，再重新双击 `macOS/安装.command`。",
            "- 如果补丁目录位于“桌面/下载/文稿”，macOS 还可能要求给 Terminal 打开对应的“文件与文件夹”开关。把补丁目录移到非受保护目录后再运行，通常更顺。",
            "- 如果补丁是从浏览器下载到另一台 Mac，这个提示更常见；没有 Apple Developer ID 签名与公证时，通常无法彻底免掉首次放行。",
            "- 提示没有权限：说明当前账户无权写入 Cursor 安装目录，请使用管理员权限。",
            "- 只拷了脚本文件：不行，必须保留 `payload/` 目录。",
            dynamic_line_zh,
            "- 运行状态、备份与回滚信息会写入 `payload/artifacts/` 与 `payload/.cursor_zh_state/`。",
            "",
            "## English",
            "",
            "This bundle is a local Cursor Chinese patch package for another computer. It includes launchers for both macOS and Windows.",
            "",
            "### Install",
            "",
            "- Copy the entire folder to the target machine. Do not copy only one script file.",
            "- macOS: for the best first-run success rate, move the bundle to a non-protected folder such as `~/work` or `~/Applications`, then run `macOS/安装.command`.",
            "- Windows: open the `Windows/` folder and double-click `Windows/安装.bat`.",
            "- To pass a custom Cursor path, run:",
            "",
            "```bash",
            "./macOS/安装.command /Applications/Cursor.app",
            "```",
            "",
            "```bat",
            "Windows\\安装.bat \"C:\\Users\\<You>\\AppData\\Local\\Programs\\Cursor\\resources\\app\"",
            "```",
            "",
            "### Rollback",
            "",
            "- macOS: open the `macOS/` folder and double-click `macOS/回滚.command`.",
            "- Windows: open the `Windows/` folder and double-click `Windows/回滚.bat`.",
            "- Rollback restores the original files backed up during patching. It does not reinstall Cursor.",
            "",
            "### Troubleshooting",
            "",
            "- Script does not open: on macOS use Right Click -> Open; on Windows try Run as administrator or execute it in Terminal/Command Prompt.",
            "- If macOS says the script is damaged or from an unidentified developer, it is usually Gatekeeper blocking an unsigned script rather than real corruption. Run `xattr -dr com.apple.quarantine \"<extracted bundle folder>\"` in Terminal, then open `macOS/安装.command` again.",
            "- If the bundle lives under Desktop, Downloads, or Documents, macOS may also ask for Terminal access to that folder. Moving the bundle to a non-protected folder usually avoids this extra prompt.",
            "- This is more common when the bundle is downloaded through a browser. Without Apple Developer ID signing and notarization, the first-run approval usually cannot be fully avoided.",
            "- Permission denied: the current account cannot write to the Cursor install directory. Run with admin privileges.",
            "- Only the script was copied: keep the whole folder, especially `payload/`.",
            dynamic_line_en,
            "- Runtime state, backups, and rollback data are stored in `payload/artifacts/` and `payload/.cursor_zh_state/`.",
            "",
        ]
    )


def build_local_bundle_install_script(enable_dynamic_market: bool) -> str:
    dynamic_flag = '--enable-dynamic-market' if enable_dynamic_market else ''
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'PAYLOAD_DIR="$ROOT_DIR/payload"',
            'TARGET_INPUT="${1:-/Applications/Cursor.app}"',
            'TARGET_APP="$TARGET_INPUT"',
            'finish(){ local status=$?; if [[ -t 0 ]]; then echo; read -r -p "按回车关闭窗口..." _; fi; exit "$status"; }',
            'log(){ echo "[install-local-patch] $*"; }',
            'resolve_cursor_app(){',
            '  if [[ "$1" == *.app ]]; then',
            '    printf "%s\\n" "$1/Contents/Resources/app"',
            "  else",
            '    printf "%s\\n" "$1"',
            "  fi",
            "}",
            'detect_python(){',
            '  local candidate',
            '  for candidate in python3 /usr/bin/python3 python; do',
            '    if command -v "$candidate" >/dev/null 2>&1; then',
            '      printf "%s\\n" "$candidate"',
            '      return 0',
            "    fi",
            "  done",
            "  return 1",
            "}",
            'is_protected_bundle_root(){',
            '  case "$1" in',
            '    "$HOME/Desktop"|"$HOME/Desktop/"*|"$HOME/Documents"|"$HOME/Documents/"*|"$HOME/Downloads"|"$HOME/Downloads/"*) return 0 ;;',
            '  esac',
            '  return 1',
            "}",
            "trap finish EXIT",
            'TARGET_APP="$(resolve_cursor_app "$TARGET_INPUT")"',
            'if [[ "${CURSOR_ZH_STAGED:-0}" != "1" ]] && is_protected_bundle_root "$ROOT_DIR"; then',
            '  STAGE_ROOT="${TMPDIR:-/tmp}/cursor-zh-stage-$$"',
            '  STAGE_DIR="$STAGE_ROOT/bundle"',
            '  mkdir -p "$STAGE_ROOT"',
            '  if command -v ditto >/dev/null 2>&1; then',
            '    ditto "$ROOT_DIR" "$STAGE_DIR"',
            "  else",
            '    cp -R "$ROOT_DIR" "$STAGE_DIR"',
            "  fi",
            '  xattr -dr com.apple.quarantine "$STAGE_DIR" 2>/dev/null || true',
            '  log "检测到补丁目录位于 macOS 受保护位置: $ROOT_DIR"',
            '  log "已复制到临时目录后继续安装，以减少首次运行时的 Terminal 文件访问拦截。"',
            '  exec env CURSOR_ZH_STAGED=1 "$STAGE_DIR/macOS/安装.command" "$TARGET_INPUT"',
            "fi",
            'xattr -dr com.apple.quarantine "$ROOT_DIR" 2>/dev/null || true',
            'if [[ ! -d "$TARGET_APP" ]]; then',
            '  echo "[install-local-patch] 未找到 Cursor 资源目录: $TARGET_APP" >&2',
            "  exit 2",
            "fi",
            'if ! PYTHON_BIN="$(detect_python)"; then',
            '  echo "[install-local-patch] 未找到 Python 3，请先安装 Python 3 再重试。" >&2',
            "  exit 3",
            "fi",
            'export PYTHONPATH="$PAYLOAD_DIR${PYTHONPATH:+:$PYTHONPATH}"',
            '"$PYTHON_BIN" -m cursor_zh apply --manifest "$PAYLOAD_DIR/patch_manifest.json" --cursor-app "$TARGET_APP" '
            + dynamic_flag,
            "",
        ]
    )


def build_local_bundle_rollback_script() -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"',
            'ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"',
            'PAYLOAD_DIR="$ROOT_DIR/payload"',
            'finish(){ local status=$?; if [[ -t 0 ]]; then echo; read -r -p "按回车关闭窗口..." _; fi; exit "$status"; }',
            'detect_python(){',
            '  local candidate',
            '  for candidate in python3 /usr/bin/python3 python; do',
            '    if command -v "$candidate" >/dev/null 2>&1; then',
            '      printf "%s\\n" "$candidate"',
            '      return 0',
            "    fi",
            "  done",
            "  return 1",
            "}",
            "trap finish EXIT",
            'xattr -dr com.apple.quarantine "$ROOT_DIR" 2>/dev/null || true',
            'if ! PYTHON_BIN="$(detect_python)"; then',
            '  echo "[rollback-local-patch] 未找到 Python 3，请先安装 Python 3 再重试。" >&2',
            "  exit 3",
            "fi",
            'export PYTHONPATH="$PAYLOAD_DIR${PYTHONPATH:+:$PYTHONPATH}"',
            '"$PYTHON_BIN" -m cursor_zh rollback --state "$PAYLOAD_DIR/.cursor_zh_state/last_apply.json"',
            "",
        ]
    )


def build_windows_python_command(py_args: str) -> str:
    return "\n".join(
        [
            "set \"PYTHON_BIN=\"",
            "where py >nul 2>nul && set \"PYTHON_BIN=py -3\"",
            "if not defined PYTHON_BIN (",
            "  where python >nul 2>nul && set \"PYTHON_BIN=python\"",
            ")",
            "if not defined PYTHON_BIN (",
            "  where python3 >nul 2>nul && set \"PYTHON_BIN=python3\"",
            ")",
            "if not defined PYTHON_BIN (",
            "  echo [cursor-zh] Python 3 not found. Please install Python 3 first.",
            "  exit /b 3",
            ")",
            f"%PYTHON_BIN% {py_args}",
        ]
    )


def build_local_bundle_install_bat(enable_dynamic_market: bool) -> str:
    dynamic_flag = " --enable-dynamic-market" if enable_dynamic_market else ""
    python_cmd = build_windows_python_command(
        ' -m cursor_zh apply --manifest "%PAYLOAD_DIR%\\patch_manifest.json" --cursor-app "%TARGET_APP%"' + dynamic_flag
    )
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            'set "SCRIPT_DIR=%~dp0"',
            'for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"',
            'set "PAYLOAD_DIR=%ROOT_DIR%\\payload"',
            'set "TARGET_APP=%~1"',
            'if not defined TARGET_APP set "TARGET_APP=%LOCALAPPDATA%\\Programs\\Cursor\\resources\\app"',
            'if not exist "%TARGET_APP%" if exist "%USERPROFILE%\\AppData\\Local\\Programs\\Cursor\\resources\\app" set "TARGET_APP=%USERPROFILE%\\AppData\\Local\\Programs\\Cursor\\resources\\app"',
            'if not exist "%TARGET_APP%" (',
            '  echo [install-local-patch] Cursor app resources directory not found: "%TARGET_APP%"',
            '  echo Usage: Windows\\安装.bat "C:\\Users\\^<You^>\\AppData\\Local\\Programs\\Cursor\\resources\\app"',
            "  exit /b 2",
            ")",
            'set "PYTHONPATH=%PAYLOAD_DIR%;%PYTHONPATH%"',
            python_cmd,
            "set EXIT_CODE=%ERRORLEVEL%",
            "if not \"%EXIT_CODE%\"==\"0\" pause",
            "exit /b %EXIT_CODE%",
            "",
        ]
    )


def build_local_bundle_rollback_bat() -> str:
    python_cmd = build_windows_python_command(
        ' -m cursor_zh rollback --state "%PAYLOAD_DIR%\\.cursor_zh_state\\last_apply.json"'
    )
    return "\r\n".join(
        [
            "@echo off",
            "setlocal",
            'set "SCRIPT_DIR=%~dp0"',
            'for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"',
            'set "PAYLOAD_DIR=%ROOT_DIR%\\payload"',
            'set "PYTHONPATH=%PAYLOAD_DIR%;%PYTHONPATH%"',
            python_cmd,
            "set EXIT_CODE=%ERRORLEVEL%",
            "if not \"%EXIT_CODE%\"==\"0\" pause",
            "exit /b %EXIT_CODE%",
            "",
        ]
    )


def copy_local_bundle_payload(payload_dir: Path) -> None:
    shutil.copytree(
        ROOT / "cursor_zh",
        payload_dir / "cursor_zh",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    shutil.copytree(ROOT / "data", payload_dir / "data", dirs_exist_ok=True)


def run_export_local_bundle(
    manifest: dict[str, Any],
    output_dir: Path | None = None,
    enable_dynamic_market: bool = False,
    create_archive: bool = False,
) -> dict[str, Any]:
    ensure_dirs()
    bundle_name = build_local_bundle_name(manifest)
    output_root = output_dir or (LOCAL_BUNDLE_DIR / bundle_name)
    if output_root.exists():
        shutil.rmtree(output_root)
    payload_dir = output_root / "payload"
    payload_dir.mkdir(parents=True, exist_ok=True)
    archive_candidate = Path(str(output_root) + ".zip")
    if archive_candidate.exists() and not create_archive:
        archive_candidate.unlink()

    portable_manifest = build_portable_manifest(manifest)
    copy_local_bundle_payload(payload_dir)
    macos_dir = output_root / "macOS"
    windows_dir = output_root / "Windows"
    macos_dir.mkdir(parents=True, exist_ok=True)
    windows_dir.mkdir(parents=True, exist_ok=True)
    write_json(payload_dir / "patch_manifest.json", portable_manifest)
    write_text(output_root / "使用说明.txt", build_local_bundle_readme(bundle_name, enable_dynamic_market))
    write_executable_text(macos_dir / "安装.command", build_local_bundle_install_script(enable_dynamic_market))
    write_executable_text(macos_dir / "回滚.command", build_local_bundle_rollback_script())
    write_text(windows_dir / "安装.bat", build_local_bundle_install_bat(enable_dynamic_market))
    write_text(windows_dir / "回滚.bat", build_local_bundle_rollback_bat())

    archive_path = shutil.make_archive(str(output_root), "zip", root_dir=output_root) if create_archive else None
    report = {
        "generated_at": now_iso(),
        "bundle_name": bundle_name,
        "output_dir": str(output_root),
        "archive_path": archive_path,
        "portable_manifest_path": str(payload_dir / "patch_manifest.json"),
        "enable_dynamic_market": enable_dynamic_market,
    }
    write_json(LOCAL_BUNDLE_DIR / "latest.json", report)
    return report


def _cmd_scan(args: argparse.Namespace) -> int:
    ctx = detect_cursor_context(Path(args.cursor_app) if args.cursor_app else None)
    report = run_scan(ctx)
    print(
        f"[scan] 已扫描 {report['summary']['target_files']} 个文件，"
        f"静态命中短语 {report['summary']['static_distinct_hit_phrases']} 个，"
        f"静态总命中 {report['summary']['static_total_phrase_hits']} 次，"
        f"核心残留提升 {report['summary']['promoted_core_phrase_items']} 项，"
        f"动态候选文本 {report['summary']['dynamic_candidate_literals']} 条。"
    )
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    scan_report = load_scan(Path(args.scan) if args.scan else None)
    manifest = run_build(scan_report)
    print(
        f"[build] 已生成 manifest，覆盖文件 {manifest['summary']['files_with_replacements']} 个，"
        f"替换项 {manifest['summary']['replacement_items']} 条，"
        f"未翻译短语 {manifest['summary']['untranslated_phrases_count']} 个。"
    )
    return 0


def _cmd_qa(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    report = run_qa(manifest)
    print(
        f"[qa] errors={report['summary']['errors']} "
        f"warnings={report['summary']['warnings']} infos={report['summary']['infos']}"
    )
    return 2 if report["summary"]["errors"] > 0 else 0


def _cmd_apply(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    cursor_app_override = Path(args.cursor_app) if args.cursor_app else None
    preview = dry_run_apply(
        manifest,
        force=args.force,
        enable_dynamic_market=args.enable_dynamic_market,
        cursor_app_override=cursor_app_override,
    )
    write_json(ARTIFACTS_DIR / "apply_preview.json", preview)
    print(
        f"[apply] dry-run 预检: 缺失文件={preview['summary']['missing_files']} "
        f"校验不一致={preview['summary']['checksum_mismatch']} "
        f"可替换次数={preview['summary']['total_replacements_preview']} "
        f"动态补丁={preview['summary']['dynamic_market_patch']} "
        f"完整性补丁={preview['summary']['integrity_patch']}"
    )
    if args.dry_run:
        return 0

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = BACKUP_DIR / timestamp
    try:
        result = apply_manifest(
            manifest,
            backup_root=backup_root,
            force=args.force,
            enable_dynamic_market=args.enable_dynamic_market,
            cursor_app_override=cursor_app_override,
        )
    except PermissionError as exc:
        print(f"[apply] 权限不足: {exc}")
        print("[apply] 请使用管理员权限执行，或先 dry-run 检查。")
        return 3
    except Exception as exc:
        print(f"[apply] 应用失败: {exc}")
        return 2
    print(
        f"[apply] 已应用成功，修改文件 {result['changed_files_count']} 个。"
        f"备份目录: {result['backup_root']}"
    )
    dynamic = result.get("dynamic_market_patch", {})
    if dynamic.get("enabled"):
        print(
            f"[apply] 动态商店补丁: applied={dynamic.get('applied')} "
            f"reason={dynamic.get('reason')} target={dynamic.get('target_path')}"
        )
    integrity = result.get("integrity_patch", {})
    print(
        f"[apply] 完整性补丁: applied={integrity.get('applied')} "
        f"reason={integrity.get('reason')} target={integrity.get('target_path')}"
    )
    return 0


def _cmd_export_local_bundle(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    report = run_export_local_bundle(
        manifest,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        enable_dynamic_market=args.enable_dynamic_market,
        create_archive=args.zip,
    )
    zip_part = f"，zip: {report['archive_path']}" if report["archive_path"] else ""
    print(f"[export-local-bundle] 已导出到 {report['output_dir']}{zip_part}")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    manifest = load_manifest(Path(args.manifest) if args.manifest else None)
    report = run_verify(manifest, threshold=args.threshold)
    summary = report["summary"]
    print(
        f"[verify] coverage={summary['coverage_percent']}% "
        f"(threshold={summary['threshold_percent']}%), "
        f"forbidden_hits={summary['forbidden_hits']}, pass={summary['pass']}"
    )
    return 0 if summary["pass"] else 2


def _cmd_rollback(args: argparse.Namespace) -> int:
    state_path = Path(args.state) if args.state else (STATE_DIR / "last_apply.json")
    if not state_path.exists():
        print(f"[rollback] 未找到状态文件: {state_path}")
        return 2
    last_apply = read_json(state_path)
    result = run_rollback(last_apply)
    print(f"[rollback] 已恢复 {result['restored_files_count']} 个文件。")
    return 0


def _cmd_upgrade(args: argparse.Namespace) -> int:
    ctx = detect_cursor_context(Path(args.cursor_app) if args.cursor_app else None)
    report = run_upgrade(ctx, threshold=args.threshold)
    dynamic = report.get("dynamic_market_target", {})
    print(
        f"[upgrade] added={len(report['diff']['added_phrases'])} "
        f"removed={len(report['diff']['removed_phrases'])} "
        f"dynamic_anchor_ok={dynamic.get('anchor_ok')} "
        f"dynamic_marker_present={dynamic.get('marker_present')} "
        f"manual_review_required={report['manual_review_required']}"
    )
    return 2 if report["manual_review_required"] else 0


def _cmd_export_store_extension(args: argparse.Namespace) -> int:
    ctx = detect_cursor_context(Path(args.cursor_app) if args.cursor_app else None)
    report = run_export_store_extension(
        ctx,
        output_dir=Path(args.output_dir) if args.output_dir else None,
        publisher=args.publisher,
        version=args.version,
    )
    print(
        f"[export-store-extension] 实验性覆盖层已导出到 {report['output_dir']}，"
        f"目标扩展 {report['summary']['target_extensions']} 个，"
        f"生成本地化 {report['summary']['localized_extensions']} 个，"
        f"翻译键 {report['summary']['translated_keys']} 个，"
        f"待补键 {report['summary']['missing_keys']} 个。"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cursor-zh", description="Cursor 全面汉化工具链")
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="扫描 Cursor 英文文案分布")
    p_scan.add_argument("--cursor-app", help="Cursor.app/Contents/Resources/app 目录")
    p_scan.set_defaults(func=_cmd_scan)

    p_build = sub.add_parser("build", help="构建版本化 patch manifest")
    p_build.add_argument("--scan", help="指定 scan 报告路径")
    p_build.set_defaults(func=_cmd_build)

    p_qa = sub.add_parser("qa", help="执行翻译质量闸门")
    p_qa.add_argument("--manifest", help="指定 patch manifest 路径")
    p_qa.set_defaults(func=_cmd_qa)

    p_apply = sub.add_parser("apply", help="应用补丁（支持 dry-run）")
    p_apply.add_argument("--manifest", help="指定 patch manifest 路径")
    p_apply.add_argument("--cursor-app", help="目标 Cursor.app/Contents/Resources/app 目录，可覆盖 manifest 内路径")
    p_apply.add_argument("--dry-run", action="store_true", help="只预检，不落盘")
    p_apply.add_argument("--force", action="store_true", help="忽略源文件校验不一致")
    p_apply.add_argument(
        "--enable-dynamic-market",
        action="store_true",
        help="启用插件市场动态简介翻译补丁（主包 JS 注入）",
    )
    p_apply.set_defaults(func=_cmd_apply)

    p_verify = sub.add_parser("verify", help="验证覆盖率与禁用词")
    p_verify.add_argument("--manifest", help="指定 patch manifest 路径")
    p_verify.add_argument("--threshold", type=float, default=98.0, help="覆盖率阈值（默认 98）")
    p_verify.set_defaults(func=_cmd_verify)

    p_rollback = sub.add_parser("rollback", help="从最近备份回滚")
    p_rollback.add_argument("--state", help="last_apply.json 路径")
    p_rollback.set_defaults(func=_cmd_rollback)

    p_upgrade = sub.add_parser("upgrade", help="更新后自动重扫/重建/复核")
    p_upgrade.add_argument("--cursor-app", help="Cursor.app/Contents/Resources/app 目录")
    p_upgrade.add_argument("--threshold", type=float, default=98.0, help="覆盖率阈值（默认 98）")
    p_upgrade.set_defaults(func=_cmd_upgrade)

    p_export_store = sub.add_parser("export-store-extension", help="导出实验性私有扩展汉化覆盖层")
    p_export_store.add_argument("--cursor-app", help="Cursor.app/Contents/Resources/app 目录")
    p_export_store.add_argument("--output-dir", help="导出目录，默认 ./beta-cursor-private-zh-overlay")
    p_export_store.add_argument("--publisher", default="beta-cursor", help="扩展发布者 / Open VSX namespace")
    p_export_store.add_argument("--version", default="0.1.0", help="扩展版本号")
    p_export_store.set_defaults(func=_cmd_export_store_extension)

    p_export_local = sub.add_parser("export-local-bundle", help="导出可跨电脑一键复现的本地补丁包")
    p_export_local.add_argument("--manifest", help="指定 patch manifest 路径")
    p_export_local.add_argument("--output-dir", help="导出目录，默认 artifacts/local_bundle/<bundle-name>")
    p_export_local.add_argument(
        "--enable-dynamic-market",
        action="store_true",
        help="安装器默认启用插件市场动态简介翻译补丁",
    )
    p_export_local.add_argument("--zip", action="store_true", help="额外生成同名 zip")
    p_export_local.set_defaults(func=_cmd_export_local_bundle)

    return parser


def main(argv: list[str] | None = None) -> int:
    ensure_dirs()
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
