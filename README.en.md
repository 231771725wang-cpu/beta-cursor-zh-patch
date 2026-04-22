# English · [中文](README.md)

<div align="center">
  <h1>Beta Cursor Zh Patch</h1>
  <p><em>"Download the real release bundle first, then add full Chinese to the Cursor you already use."</em></p>
  <p>
    <a href="./LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-5b5b5b"></a>
    <a href="https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2"><img alt="Release: v0.2.2" src="https://img.shields.io/badge/Release-v0.2.2-2f2f2f"></a>
    <img alt="Install: Release ZIP" src="https://img.shields.io/badge/Install-Release_ZIP-111111">
    <img alt="Platform: macOS and Windows" src="https://img.shields.io/badge/Platform-macOS%20%7C%20Windows-1f6feb">
    <img alt="Rollback Included" src="https://img.shields.io/badge/Rollback-Included-7a3cff">
  </p>
</div>

> "No reinstall. No replacement build. Just add full Chinese to the Cursor installation you already have."

**Beta Cursor Zh Patch** ships as a real end-user release bundle and a maintainer-friendly source repository. End users should start from the GitHub Release ZIP: extract it, run the installer script, and patch an existing Cursor installation locally.

The source repository is for maintainers who need to continue `scan / build / qa / apply / verify / rollback / export-*`. The homepage should make this split obvious from the first screen instead of making users guess between a source archive and the real install bundle.

If what you want is not a demo but a shippable local patch with rollback still within reach, this is the package.

**Release page:** [v0.2.2](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2)  
**Direct ZIP:** [Beta-Cursor-全面汉化-3.1.17-fce1e9ab.zip](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/download/v0.2.2/Beta-Cursor-%E5%85%A8%E9%9D%A2%E6%B1%89%E5%8C%96-3.1.17-fce1e9ab.zip)

## Preview

![Beta Cursor Zh Patch Preview](assets/beta-cursor-zh-patch-preview.svg)

## Install For End Users

1. Download the real ZIP bundle from the [Release page](https://github.com/231771725wang-cpu/beta-cursor-zh-patch/releases/tag/v0.2.2), not the source archive.
2. Extract it, then run:
   - macOS: `macOS/安装.command`
   - Windows: `Windows/安装.bat`
3. Use the bundled rollback path if you need to revert the patch later.

## What You Get

- A real Release bundle for non-technical users
- Local patching for an existing Cursor install instead of reinstalling another copy
- Rollback scripts, verification flow, and local state bundled together
- The source workflow maintainers need to rebuild and export future bundles
- Before/after screenshots that show the result directly

## Before / After

| Before | After |
| --- | --- |
| ![Before 1](对比截图/前1.png) | ![After 1](对比截图/汉1.png) |
| ![Before 2](对比截图/前2.png) | ![After 2](对比截图/汉2.png) |
| ![Before 3](对比截图/前3.png) | ![After 3](对比截图/汉3.png) |

## Maintainer Entry

Clone the repository only if you are maintaining the patch pipeline:

```bash
git clone git@github.com:231771725wang-cpu/beta-cursor-zh-patch.git
cd beta-cursor-zh-patch
```

Common commands:

```bash
./cursor-zh scan --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh build
./cursor-zh qa
./cursor-zh apply --cursor-app /Applications/Cursor.app/Contents/Resources/app
./cursor-zh verify
./cursor-zh rollback
./cursor-zh export-local-bundle --zip
```

Experimental overlay export:

```bash
./cursor-zh export-store-extension
```

## Boundaries

- This is a local patch workflow, not an official Cursor language pack.
- The release bundle modifies an existing Cursor installation; it does not install another copy of Cursor.
- Runtime state, rollback data, and backups remain local.
- Cursor updates can change hard-coded strings, extension keys, and scan targets, so new versions may require rescanning and rebuilding.

## Project Layout

- `cursor_zh/`: core CLI and patch logic
- `data/`: translations, glossary, and coverage data
- `payload/patch_manifest.json`: versioned patch manifest bundled with the repo
- `beta-cursor-hanhua/`: experimental overlay layer for private-extension-visible strings
- `tests/`: CLI and bundle tests
- `对比截图/`: before/after screenshots used on the GitHub landing page

## Disclaimer

This project is not affiliated with Cursor. Use it only on installations you are authorized to modify.
