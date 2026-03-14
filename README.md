# Beta Cursor 全面汉化补丁

这是一个面向 Cursor Beta 版本的本地汉化补丁仓库，目标是尽量在不改动日常使用方式的前提下，把 Cursor 的核心设置、智能体相关页面和常见界面文案翻译成简体中文。

本仓库只包含补丁脚本、翻译数据和说明，不包含 Cursor 原始安装包或官方资源备份文件。

## 截图对比

### General / 通用

| Before | After |
| --- | --- |
| ![Before General](assets/screenshots/before-general.png) | ![After General](assets/screenshots/after-general.png) |

### Agents / 智能体

| Before | After |
| --- | --- |
| ![Before Agents](assets/screenshots/before-agents.png) | ![After Agents](assets/screenshots/after-agents.png) |

### Rules, Skills, Subagents / 规则、技能、子智能体

| Before | After |
| --- | --- |
| ![Before Rules, Skills, Subagents](assets/screenshots/before-rules-skills-subagents.png) | ![After Rules, Skills, Subagents](assets/screenshots/after-rules-skills-subagents.png) |

## 当前状态

- macOS（Apple Silicon）已验证可用
- Windows 已补充启动器与 GitHub Actions 脚本级冒烟验证，但暂未做作者本人实机长时间验证
- 仓库默认附带 macOS 与 Windows 两套安装/回滚入口

## 安装

详细说明见 [使用说明.txt](使用说明.txt)。

### macOS

1. 下载或克隆仓库后，先把目录移到 `~/work`、`~/Applications` 或其他非“桌面/下载/文稿”位置。
2. 进入 `macOS/`，运行 `安装.command`。
3. 如遇到 Gatekeeper 提示，可先执行：

```bash
xattr -dr com.apple.quarantine "<仓库目录>"
```

4. 如需手动指定 Cursor 路径，可运行：

```bash
./macOS/安装.command /Applications/Cursor.app
```

### Windows

1. 进入 `Windows/`，运行 `安装.bat`。
2. 默认会尝试查找：

```text
C:\Users\<You>\AppData\Local\Programs\Cursor\resources\app
```

3. 如需手动指定路径，可运行：

```bat
Windows\安装.bat "C:\Users\<You>\AppData\Local\Programs\Cursor\resources\app"
```

## 回滚

- macOS：运行 `macOS/回滚.command`
- Windows：运行 `Windows/回滚.bat`

## 项目结构

- `payload/cursor_zh/`：补丁主逻辑
- `payload/data/`：翻译数据、术语表与覆盖短语
- `macOS/`：macOS 安装与回滚入口
- `Windows/`：Windows 安装与回滚入口
- `assets/screenshots/`：README 对比截图

## 注意事项

- 这是本地补丁，不是 Cursor 官方语言包
- 首次从浏览器下载到 macOS 时，系统可能会拦截未签名脚本，这是系统安全策略，不代表补丁损坏
- 如果补丁目录位于“桌面/下载/文稿”，macOS 还可能要求给 Terminal 打开“文件与文件夹”权限
- 发布到 GitHub 时，建议使用 Releases 分发 ZIP，避免直接让用户复制零散文件

## 免责声明

本项目与 Cursor 官方无关，仅供个人学习、界面本地化和交流使用。请在你拥有合法 Cursor 使用权的前提下使用本补丁。

## 许可证

待发布时确认。  
如果你想要一个对首个开源项目最省心的方案，推荐使用 `MIT License`。
