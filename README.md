# Beta Cursor 中文完整本地化方案

[![Release](https://img.shields.io/github/v/release/231771725wang-cpu/beta-cursor-zh-patch?label=Release)](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases)
[![License](https://img.shields.io/github/license/231771725wang-cpu/beta-cursor-zh-patch?label=License)](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/blob/main/LICENSE)

这不是一个“给官方语言包打补丁”的附属项目，而是一套面向 Cursor Beta 的独立完整本地化方案。

它要解决的不是“把能翻的地方顺手翻一下”，而是把 Cursor 真正做成一套对中文用户足够完整、足够连贯、足够像原生产品的使用体验。为此，它会直接处理核心设置、Agents、Rules / Skills / Subagents，以及标准语言包碰不到的主程序硬编码文案。

如果你要的是一个可安装、可回滚、可导出、可分发、可长期维护的中文主方案，而不是一层依附官方语言包的零散补丁，这个仓库就是为那件事做的。

本仓库只包含补丁脚本、翻译数据和说明，不包含 Cursor 原始安装包或官方资源备份文件。

## 亮点

- 独立定位：不把官方简体中文语言包当主路径，而是把“完整中文体验”本身当成一等目标。
- 深度覆盖：不只翻公开接口，也补齐 Cursor 私有界面、Agents 工作流和主程序硬编码文案。
- 工程化交付：既能直接本地应用补丁，也能导出可跨电脑复现的补丁包和实验性扩展覆盖层。

## 截图对比

### 示例一

| Before | After |
| --- | --- |
| ![Before 1](对比截图/前1.png) | ![After 1](对比截图/汉1.png) |

### 示例二

| Before | After |
| --- | --- |
| ![Before 2](对比截图/前2.png) | ![After 2](对比截图/汉2.png) |

### 示例三

| Before | After |
| --- | --- |
| ![Before 3](对比截图/前3.png) | ![After 3](对比截图/汉3.png) |

## 当前状态

- `cursor-zh apply` 是本地完整补丁的主入口。
- `export-local-bundle` 是跨电脑分发的主路径。
- `export-store-extension` 仅保留为实验性附属产物，不等价于完整汉化。
- 仓库当前包含 CLI 源码、翻译数据、测试与实验性扩展产物。

## 使用方式

### 直接本地应用

```bash
./cursor-zh apply --help
```

常用相关命令：

```bash
./cursor-zh verify
./cursor-zh rollback
./cursor-zh upgrade
```

### 导出完整补丁包

```bash
./cursor-zh export-local-bundle
```

导出的 bundle 用于另一台电脑时，可配合仓库中的 [使用说明.txt](使用说明.txt) 理解安装、回滚和常见问题。

### 导出实验性扩展覆盖层

```bash
./cursor-zh export-store-extension
```

这一产物只覆盖 Cursor 私有扩展中已暴露到 `package.nls.json` 的文案，不能替代主补丁链。

## 产物路线

- 主产物：`./cursor-zh apply` 直接应用的本地完整补丁，以及 `./cursor-zh export-local-bundle` 导出的 bundle。
- 实验产物：`beta-cursor-hanhua/` 目录对应的私有扩展汉化覆盖层。
- 如果你追求和截图接近的覆盖率，应优先使用主产物；实验产物只适合补充标准本地化接口可见的那部分文案。

## 项目结构

- `cursor_zh/`：补丁主逻辑与 CLI 实现。
- `data/`：翻译数据、术语表与覆盖短语。
- `payload/patch_manifest.json`：版本化补丁清单。
- `beta-cursor-hanhua/`：实验性扩展覆盖层产物。
- `tests/`：CLI 与导出链路测试。
- `cursor-zh`：仓库根目录启动脚本。

## 注意事项

- 这是本地补丁方案，不是 Cursor 官方语言包。
- 主方案不以官方简体中文语言包为前提；是否叠加官方语言包，应按你的覆盖需求决定。
- Cursor 一旦升级版本，主程序结构、私有扩展键名或硬编码文案可能变化，必要时需要重新适配或重新导出。
- 如果你希望对外稳定分发，优先发布 `export-local-bundle` 的产物，而不是让用户手动拼装仓库文件。

## 免责声明

本项目与 Cursor 官方无关，仅供个人学习、界面本地化和交流使用。请在你拥有合法 Cursor 使用权的前提下使用本补丁。
