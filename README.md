# Beta Cursor 中文完整本地化方案

[![Release](https://img.shields.io/github/v/release/231771725wang-cpu/beta-cursor-zh-patch?label=Release)](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases)
[![License](https://img.shields.io/github/license/231771725wang-cpu/beta-cursor-zh-patch?label=License)](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/blob/main/LICENSE)

这是源码仓库，不是给普通用户直接双击安装的成品目录。

如果你是普通用户，请不要下载 GitHub 的 Source code zip 直接照着仓库根目录操作。对外分发的主产物是 GitHub Releases 里的 `export-local-bundle` 导出包；那个包自带 `macOS/安装.command`、`Windows/安装.bat`、回滚脚本和面向终端用户的安装说明。

## 你应该下载什么

- 普通用户：下载 GitHub Releases 里的 `Beta-Cursor-全面汉化-<version>-<commit>.zip` 或同名目录包。
- 开发者 / 维护者：克隆这个源码仓库，使用 CLI 做扫描、构建、应用、验证和导出。

Release bundle 的行为边界：

- 只会修改目标机器上已经安装好的 Cursor。
- 不会下载、复制或安装第二个 Cursor。
- 运行状态、备份和回滚信息写在 bundle 自己的 `payload/artifacts/` 与 `payload/.cursor_zh_state/` 下。
- 备份会占用额外磁盘空间；确认不再需要回滚后，可删除 `payload/artifacts/backups/`。

## 开发者工作流

前置条件：

- Python 3.9+
- 一份可访问的 Cursor 安装目录

常用命令：

```bash
./cursor-zh scan --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh build
./cursor-zh qa
./cursor-zh apply --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh verify
./cursor-zh rollback
```

跨电脑分发 bundle：

```bash
./cursor-zh export-local-bundle --zip
```

实验性 overlay 扩展：

```bash
./cursor-zh export-store-extension
```

## 项目结构

- `cursor_zh/`：补丁主逻辑与 CLI。
- `data/`：翻译数据、术语表与覆盖短语。
- `payload/patch_manifest.json`：当前仓库附带的版本化补丁清单。
- `beta-cursor-hanhua/`：实验性私有扩展汉化覆盖层快照，不是主安装路径。
- `tests/`：CLI、bundle 与导出链路测试。
- `cursor-zh`：仓库根目录启动脚本。

## 产物边界

- 主产物：`export-local-bundle` 导出的本地完整补丁包，适合 GitHub Releases 分发。
- 源码能力：`scan/build/apply/verify/rollback/export-*`，适合开发和维护。
- 附属产物：`beta-cursor-hanhua/` overlay，只覆盖标准本地化接口可见的私有扩展文案，不能替代完整补丁链。

## 注意事项

- 这是本地补丁方案，不是 Cursor 官方语言包。
- Cursor 升级后，主程序结构、私有扩展键名和硬编码文案都可能变化，必要时需要重新扫描、重新构建或重新导出。
- 如果你打算给别人用，优先发布 release bundle，不要让普通用户直接在源码仓库里找安装入口。

## 免责声明

本项目与 Cursor 官方无关，仅供个人学习、界面本地化和交流使用。请在你拥有合法 Cursor 使用权的前提下使用本补丁。
