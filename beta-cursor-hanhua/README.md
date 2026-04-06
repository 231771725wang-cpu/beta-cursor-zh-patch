# Beta Cursor 私有扩展汉化覆盖层（实验）

这是一个实验性的 Cursor 私有扩展汉化覆盖层，用于补充标准本地化接口可见的 Cursor 私有扩展文案。

它不是仓库主产物，也不等价于本仓库的本地完整汉化补丁。

## 能力边界

- 仅覆盖 Cursor 自带私有扩展里已经暴露到 `package.nls.json` 的文案。
- 不修改 Cursor.app 主程序文件，适合打包为 VSIX 或作为实验性附属产物分发。
- 不覆盖 `workbench.desktop.main.js` 等主程序硬编码文案；这部分仍需仓库根目录的 `cursor-zh apply` 补丁链处理。

## 当前生成信息

- 目标 Cursor 版本: `3.0.12`
- 目标提交哈希: `a80ff7dfcaa45d7750f6e30be457261379c29b00`
- 扩展名: `beta-cursor-hanhua`
- 已生成本地化目标: `3` 个
- 无法导出到商店语言包的 Cursor 内置扩展: `15` 个

## 已覆盖的 Cursor 内置扩展

- `anysphere.cursor-always-local`: 2 个键
- `anysphere.cursor-retrieval`: 2 个键
- `anysphere.cursor-shadow-workspace`: 2 个键

## 兼容性

- 这是标准 VSIX 语言包扩展，不限定 macOS / Windows / Linux。
- 只要对应版本的 Cursor 在各平台上使用相同的私有扩展 ID 与本地化键，这个包就可复用。
- 当前导出基于 Cursor `3.0.12`，如后续版本变更了扩展 ID 或键名，请先重新执行导出。

## 安装方式

1. 安装本扩展的 `.vsix`，然后重载 Cursor。
2. 若仍有未汉化区域，说明它属于 Cursor 主程序硬编码文案或未暴露到标准本地化接口的私有界面，请改用本仓库根目录的完整补丁链。
3. 如果你还想补齐 Cursor / VS Code 公共界面的通用简体中文，可额外叠加官方简体中文语言包，但这不是本扩展的前置条件。

## 当前无法直接做成商店语言包的内置扩展

- `anysphere.cursor-agent`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-agent-exec`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `cursor.cursor-browser-automation`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-checkout`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-commits`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-deeplink`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-explorer`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-file-service`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-mcp`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-ndjson-ingest`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-polyfills-remote`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-resolver`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-resolver-helper`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `anysphere.cursor-socket`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造
- `everysphere.worktree-textmate`: 缺少 `package.nls.json`，只能靠本地补丁或上游改造

## 重新生成

```bash
./cursor-zh export-store-extension
```

可选参数：

- `--publisher your-openvsx-namespace`
- `--version 0.2.0`
- `--output-dir ./beta-cursor-hanhua`

## 打包与发布

```bash
cd beta-cursor-hanhua
./scripts/package-openvsx.sh
OPEN_VSX_TOKEN=xxxx ./scripts/publish-openvsx.sh
```

## 边界说明

- 该覆盖层只承载标准本地化接口可见的文案。
- 直接改主程序 JS 的完整汉化部分，不能等价迁移成纯语言包或纯覆盖层。
- 如需接近本仓库当前覆盖率，应优先使用仓库根目录的本地完整补丁版。
- `beta-cursor-hanhua/`：实验性私有扩展汉化覆盖层。
- 仓库根目录 `cursor-zh`：本地完整补丁版。
