# [English](README.en.md) · 中文

<div align="center">
  <h1>Beta Cursor 中文完整本地化方案</h1>
  <p><em>“先下真正可安装的 Release 包，再给你手里的 Cursor 直接装上中文。”</em></p>
  <p>
    <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-5b5b5b"></a>
    <a href="https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2"><img alt="Release: v0.2.2" src="https://img.shields.io/badge/Release-v0.2.2-2f2f2f"></a>
    <img alt="安装方式：Release ZIP" src="https://img.shields.io/badge/Install-Release_ZIP-111111">
    <img alt="平台：macOS 和 Windows" src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-1f6feb">
    <img alt="Rollback Included" src="https://img.shields.io/badge/Rollback-Included-7a3cff">
  </p>
</div>

> “不重装，不换壳，直接给现有 Cursor 加上完整中文。”

**Beta Cursor 中文完整本地化方案** 是一套面向普通用户可直接安装、面向维护者可继续迭代的本地补丁交付。你下载的不是源码示例，也不是半成品脚本，而是一份已经打包好的 Release ZIP：解压、运行安装脚本、给现有 Cursor 直接上中文。

普通用户的正确入口是 GitHub Release；源码仓库则留给维护者继续做 `scan / build / qa / apply / verify / rollback / export-*`。这两条路径从首页一开始就应该分开，不再让用户在 `Source code.zip` 和真正安装包之间自己猜。

如果你要的不是“看个思路”，而是“真装上去、还能回滚、还能继续维护”，这就是那套交付物。

**下载发布页：** [v0.2.2](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2)  
**直接下载 ZIP：** [Beta-Cursor-.-3.1.17-fce1e9ab.zip](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/download/v0.2.2/Beta-Cursor-.-3.1.17-fce1e9ab.zip)  
**英文说明：** [README.en.md](README.en.md)

## 预览

![Beta Cursor 中文完整本地化方案预览](assets/beta-cursor-zh-patch-preview.svg)

## 普通用户安装

1. 先从 [Release 页面](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2) 下载真正的 ZIP 补丁包，不要下载源码压缩包。
2. 解压之后：
   - macOS：运行 `macOS/安装.command`
   - Windows：运行 `Windows/安装.bat`
3. 如果后面想撤回修改，直接使用包内保留的回滚链路。

## 你会得到什么

- 一份面向普通用户的真实 Release 安装包
- 基于现有 Cursor 安装直接打补丁，而不是重装另一个 Cursor
- 回滚脚本、校验链路和本地状态一起打包
- 同时保留维护者继续扫描、构建、验证和再次导出的源码能力
- 一组可直接证明效果的汉化前后截图

## 前后对比

| 汉化前 | 汉化后 |
| --- | --- |
| ![汉化前 1](对比截图/前1.png) | ![汉化后 1](对比截图/汉1.png) |
| ![汉化前 2](对比截图/前2.png) | ![汉化后 2](对比截图/汉2.png) |
| ![汉化前 3](对比截图/前3.png) | ![汉化后 3](对比截图/汉3.png) |

## 维护者入口

如果你要维护补丁链路，而不是单纯安装，才进入源码仓库：

```bash
git clone git@github.com:231771725wang-cpu/beta-cursor-zh-patch.git
cd beta-cursor-zh-patch
```

常用命令：

```bash
./cursor-zh scan --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh build
./cursor-zh qa
./cursor-zh apply --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh verify
./cursor-zh rollback
./cursor-zh export-local-bundle --zip
```

实验性 overlay 导出：

```bash
./cursor-zh export-store-extension
```

## 边界说明

- 这是一套本地补丁方案，不是 Cursor 官方语言包。
- Release 补丁包只会修改你机器上已经安装好的 Cursor，不会额外安装另一个 Cursor。
- 运行状态、回滚信息和备份都保留在本地 payload 内，不依赖远程服务。
- Cursor 升级后，硬编码文案、私有扩展键名和扫描目标都可能变化，所以新版本往往需要重新扫描、重新构建和重新导出。

## 项目结构

- `cursor_zh/`：CLI 与补丁主逻辑
- `data/`：翻译、术语表与覆盖率数据
- `payload/patch_manifest.json`：随仓库附带的版本化补丁清单
- `beta-cursor-hanhua/`：实验性 overlay 层，只覆盖部分私有扩展可见文案
- `tests/`：CLI 与 bundle 测试
- `对比截图/`：GitHub 首页使用的前后对比截图

## 免责声明

本项目与 Cursor 官方无关。请仅在你有权修改的 Cursor 安装上使用。
