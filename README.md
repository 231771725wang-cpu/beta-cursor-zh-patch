# cursor-zh

面向 Cursor 的“双层汉化”工具链：

- 完整补丁版：官方语言包 + 私有文案补丁 + 插件市场动态简介补丁
- 商店安全版：导出为 Open VSX / Cursor 可发布的语言包扩展

## 最新验证

- 已重新适配并验证 Cursor `2.6.21`
- 目标提交哈希: `fea2f546c979a0a4ad1deab23552a43568807590`
- 2026-03-26 已确认欢迎页与设置页关键运行时文案补丁生效

## 能力

- `scan`: 扫描 Cursor 私有英文文案命中，并区分静态可替换与动态候选文本
- `build`: 构建版本化 `patch_manifest`
- `qa`: 执行占位符/术语/禁用词质检
- `apply`: 支持 dry-run 与实际应用，自动备份；默认同步运行时完整性补丁，可选注入插件市场动态汉化补丁
- `export-local-bundle`: 导出可拷到下一台电脑上直接运行的本地汉化补丁包（macOS + Windows）
- `verify`: 产出 `coverage_report` 并按阈值验收
- `rollback`: 从最近备份一键回滚
- `upgrade`: 更新后自动重扫/重建/复核，并检查动态补丁锚点有效性
- `export-store-extension`: 生成 `Beta-cursor 汉化` 扩展骨架，补充 Cursor 私有扩展的标准本地化键

## 目录

- `data/glossary`: 术语与禁用词
- `data/translations/custom_phrases.json`: 私有文案翻译映射
- `data/translations/dynamic_market_phrases.json`: 插件市场动态简介翻译映射
- `data/coverage/core_phrases.json`: 覆盖率核心短语
- `artifacts/patch_manifest`: 版本补丁清单
- `artifacts/coverage_report`: 覆盖率报告

## 用法

```bash
./cursor-zh scan
./cursor-zh build
./cursor-zh qa
./cursor-zh apply --dry-run
./cursor-zh apply
./cursor-zh apply --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh apply --enable-dynamic-market
./cursor-zh export-local-bundle
./cursor-zh export-local-bundle --enable-dynamic-market
./cursor-zh export-local-bundle --zip
./cursor-zh verify --threshold 98
./cursor-zh rollback
./cursor-zh upgrade --threshold 98
./cursor-zh export-store-extension
```

> `apply` 默认会修正 Cursor 运行时完整性检查，避免补丁后继续出现 “installation appears to be corrupt” 误报；这不会恢复 macOS 官方签名。
> 若写入 `/Applications/Cursor.app` 提示权限不足，请使用管理员权限执行 `apply`，或先在桌面副本上应用后手动替换。
> 动态补丁在锚点不匹配时会自动降级为只读告警，不会注入高风险改动。

## 跨电脑一键复现

```bash
./cursor-zh export-local-bundle
```

- 默认导出到 `artifacts/local_bundle/<bundle-name>/`，保留完整目录版
- 如需分发压缩包，可追加 `--zip` 生成同名 `.zip`
- 产物内包含 macOS 的 `安装-macOS.command` / `回滚-macOS.command`
- 也包含 Windows 的 `安装-Windows.bat` / `回滚-Windows.bat`
- 附带 `使用说明.txt`，提供中英双语安装、回滚与排障说明
- 拷到另一台电脑后可直接双击；如需指定路径，也可在终端或 CMD 里传入目标 Cursor `resources/app` 目录

如需给 GitHub Release 提供可下载附件，建议使用：

```bash
./cursor-zh export-local-bundle --zip
```

推荐把生成的 `Beta-Cursor-全面汉化-<version>-<commit>.zip` 作为 release asset 上传。

## 商店版与完整补丁版的边界

- `export-store-extension` 只导出 Cursor 已暴露给标准本地化系统的文案，例如部分 `cursor-*` 内置扩展的 `package.nls.json`。
- 直接写死在 `workbench.desktop.main.js`、`out/nls.messages.json` 或其他主程序资源里的私有文案，不能等价迁移为纯语言包扩展。
- 因此要想“像插件一样上架”并同时保持当前这套高覆盖率，建议维护两条产线：
- `beta-cursor-hanhua/`：给 Open VSX / Cursor 商店上架的安全版。
- 根目录 `cursor-zh` CLI：给本地用户用的完整补丁版。
