# Beta Cursor 中文完整本地化方案

面向 Cursor 的商店安全版汉化增强扩展，优先补足官方简体中文语言包尚未覆盖的 Cursor 私有扩展文案。

这不是一个“给官方语言包打补丁”的附属项目，而是一套面向 Cursor Beta 的独立完整本地化方案。

它要解决的不是“把能翻的地方顺手翻一下”，而是把 Cursor 真正做成一套对中文用户足够完整、足够连贯、足够像原生产品的使用体验。为此，它会直接处理核心设置、Agents、Rules / Skills / Subagents，以及标准语言包碰不到的主程序硬编码文案。

如果你要的是一个可安装、可回滚、可导出、可分发、可长期维护的中文主方案，而不是一层依附官方语言包的零散补丁，这个仓库就是为那件事做的。

- 依赖官方简体中文语言包，补充 Cursor 自带私有扩展里已暴露到 `package.nls.json` 的文案。
- 不修改 Cursor.app 主程序文件，适合打包为 VSIX 并发布到 Open VSX / Cursor 扩展发现链路。
- 不覆盖 `workbench.desktop.main.js` 里的硬编码文案；这部分仍需仓库根目录的 `cursor-zh apply` 补丁链处理。

## 亮点

- 独立定位：不把官方简体中文语言包当主路径，而是把“完整中文体验”本身当成一等目标。
- 深度覆盖：不只翻公开接口，也补齐 Cursor 私有界面、Agents 工作流和主程序硬编码文案。
- 工程化交付：默认提供 macOS / Windows 安装、回滚与 bundle 导出能力，适合自用，也适合稳定分发。

## 截图对比

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

1. 在 Cursor 中先安装官方简体中文语言包 `MS-CEINTL.vscode-language-pack-zh-hans`。
2. 安装本扩展的 `.vsix`，然后重载 Cursor。
3. 若仍有未汉化区域，属于 Cursor 主程序硬编码文案，请配合本仓库根目录的完整补丁版使用。

- macOS（Apple Silicon）已验证可用
- Windows 已补充启动器与 GitHub Actions 脚本级冒烟验证，但暂未做作者本人实机长时间验证
- 仓库默认附带 macOS 与 Windows 两套安装/回滚入口
- `export-local-bundle` 是主分发路径；`export-store-extension` 仅保留为实验性附属产物

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

1. 进入 `Windows/`，运行 `安装.bat`。
2. 默认会尝试查找：

```text
C:\Users\<You>\AppData\Local\Programs\Cursor\resources\app
```

3. 如需手动指定路径，可运行：

```bat
Windows\安装.bat "C:\Users\<You>\AppData\Local\Programs\Cursor\resources\app"
```

## 产物路线

- 主产物：仓库根目录安装/回滚入口，以及 `python -m cursor_zh export-local-bundle` 导出的本地完整补丁 bundle。
- 实验产物：`python -m cursor_zh export-store-extension` 导出的私有扩展汉化覆盖层，只覆盖 Cursor 私有扩展中已暴露到 `package.nls.json` 的文案。
- 如果你追求和本仓库截图接近的覆盖率，应优先使用主产物；实验产物不等价于完整汉化。
- 如需额外补齐 Cursor / VS Code 公共界面的通用简体中文，可自行叠加官方简体中文语言包，但这不是本项目主产物的前置条件。

## 回滚

- macOS：运行 `macOS/回滚.command`
- Windows：运行 `Windows/回滚.bat`

## 项目结构

- `payload/cursor_zh/`：补丁主逻辑
- `payload/data/`：翻译数据、术语表与覆盖短语
- `macOS/`：macOS 安装与回滚入口
- `Windows/`：Windows 安装与回滚入口
- `assets/screenshots/`：README 对比截图
- `beta-cursor-private-zh-overlay/`：实验性私有扩展汉化覆盖层的默认导出目录

## 注意事项

- 这是本地补丁，不是 Cursor 官方语言包
- 主产物可独立工作；官方简体中文语言包最多只是可选叠加，不是必装依赖
- 首次从浏览器下载到 macOS 时，系统可能会拦截未签名脚本，这是系统安全策略，不代表补丁损坏
- 如果补丁目录位于“桌面/下载/文稿”，macOS 还可能要求给 Terminal 打开“文件与文件夹”权限
- 发布到 GitHub 时，建议使用 Releases 分发 ZIP，避免直接让用户复制零散文件

## 免责声明

本项目与 Cursor 官方无关，仅供个人学习、界面本地化和交流使用。请在你拥有合法 Cursor 使用权的前提下使用本补丁。

## 许可证

待发布时确认。  
如果你想要一个对首个开源项目最省心的方案，推荐使用 `MIT License`。
