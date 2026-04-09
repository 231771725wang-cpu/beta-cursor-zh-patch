from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
import unittest.mock as mock
from pathlib import Path

from cursor_zh.cli import (
    AUTO_HEAL_LABEL,
    CursorContext,
    apply_manifest,
    build_auto_heal_launch_agent_plist,
    build_parser,
    collect_product_checksum_updates,
    collect_qa_issues,
    dry_run_apply,
    disable_integrity_service,
    read_text,
    run_auto_heal,
    run_build,
    run_export_local_bundle,
    run_export_store_extension,
    run_rollback,
    run_scan,
    run_verify,
    sha256_file_base64,
    sha256_text,
    upsert_dynamic_market_patch,
    write_json,
)


class CursorZhTests(unittest.TestCase):
    def setUp(self) -> None:
        import cursor_zh.cli as mod

        super().setUp()
        self._sandbox = tempfile.TemporaryDirectory()
        sandbox_root = Path(self._sandbox.name)
        self._old_paths = {
            "ARTIFACTS_DIR": mod.ARTIFACTS_DIR,
            "STATE_DIR": mod.STATE_DIR,
            "SCAN_DIR": mod.SCAN_DIR,
            "PATCH_MANIFEST_DIR": mod.PATCH_MANIFEST_DIR,
            "QA_DIR": mod.QA_DIR,
            "BACKUP_DIR": mod.BACKUP_DIR,
            "COVERAGE_DIR": mod.COVERAGE_DIR,
            "UPGRADE_DIR": mod.UPGRADE_DIR,
            "STORE_EXTENSION_ARTIFACTS_DIR": mod.STORE_EXTENSION_ARTIFACTS_DIR,
            "LOCAL_BUNDLE_DIR": mod.LOCAL_BUNDLE_DIR,
            "LOGS_DIR": mod.LOGS_DIR,
            "AUTO_HEAL_STATUS_PATH": mod.AUTO_HEAL_STATUS_PATH,
            "AUTO_HEAL_LOG_PATH": mod.AUTO_HEAL_LOG_PATH,
            "AUTO_HEAL_ERR_LOG_PATH": mod.AUTO_HEAL_ERR_LOG_PATH,
        }

        mod.ARTIFACTS_DIR = sandbox_root / "artifacts"
        mod.STATE_DIR = sandbox_root / ".cursor_zh_state"
        mod.SCAN_DIR = mod.ARTIFACTS_DIR / "scan"
        mod.PATCH_MANIFEST_DIR = mod.ARTIFACTS_DIR / "patch_manifest"
        mod.QA_DIR = mod.ARTIFACTS_DIR / "qa"
        mod.BACKUP_DIR = mod.ARTIFACTS_DIR / "backups"
        mod.COVERAGE_DIR = mod.ARTIFACTS_DIR / "coverage_report"
        mod.UPGRADE_DIR = mod.ARTIFACTS_DIR / "upgrade"
        mod.STORE_EXTENSION_ARTIFACTS_DIR = mod.ARTIFACTS_DIR / "store_extension"
        mod.LOCAL_BUNDLE_DIR = mod.ARTIFACTS_DIR / "local_bundle"
        mod.LOGS_DIR = mod.ARTIFACTS_DIR / "logs"
        mod.AUTO_HEAL_STATUS_PATH = mod.STATE_DIR / "auto_heal_status.json"
        mod.AUTO_HEAL_LOG_PATH = mod.LOGS_DIR / "auto-heal.log"
        mod.AUTO_HEAL_ERR_LOG_PATH = mod.LOGS_DIR / "auto-heal.err.log"

    def tearDown(self) -> None:
        import cursor_zh.cli as mod

        for key, value in self._old_paths.items():
            setattr(mod, key, value)
        self._sandbox.cleanup()
        super().tearDown()

    def _make_auto_heal_app(self, root: Path, version: str, commit: str, *, workbench_text: str = "const demo = 1;\n") -> CursorContext:
        app = root / "Cursor.app" / "Contents" / "Resources" / "app"
        nls = app / "out" / "nls.messages.json"
        workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
        nls.parent.mkdir(parents=True, exist_ok=True)
        workbench.parent.mkdir(parents=True, exist_ok=True)
        nls.write_text('"Hello"\n', encoding="utf-8")
        workbench.write_text(workbench_text, encoding="utf-8")
        write_json(app / "product.json", {"commit": commit, "checksums": {}})
        write_json(app / "package.json", {"version": version})
        return CursorContext(
            app_path=app,
            package_path=app / "package.json",
            product_path=app / "product.json",
            version=version,
            commit=commit,
            lang_pack_path=None,
        )

    def _set_fake_auto_heal_data(self, root: Path) -> tuple[Path, Path]:
        import cursor_zh.cli as mod

        old_data_dir = mod.DATA_DIR
        fake_data = root / "data"
        (fake_data / "translations").mkdir(parents=True, exist_ok=True)
        (fake_data / "coverage").mkdir(parents=True, exist_ok=True)
        (fake_data / "glossary").mkdir(parents=True, exist_ok=True)
        write_json(fake_data / "translations" / "custom_phrases.json", {"Hello": "你好"})
        write_json(fake_data / "translations" / "dynamic_market_phrases.json", {"Published by": "发布者"})
        write_json(fake_data / "coverage" / "core_phrases.json", [])
        write_json(fake_data / "glossary" / "forced_terms.json", {})
        write_json(fake_data / "glossary" / "keep_english_terms.json", [])
        write_json(fake_data / "glossary" / "forbidden_terms.json", [])
        mod.DATA_DIR = fake_data
        return old_data_dir, fake_data

    def test_auto_heal_skips_when_current_version_already_successful(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_auto_heal_app(root, "2.6.22", "c6285fea")
            state_path = root / ".cursor_zh_state" / "auto_heal_status.json"
            write_json(
                state_path,
                {
                    "last_success": {"version": "2.6.22", "commit": "c6285fea"},
                    "last_result": {"status": "applied"},
                },
            )

            result = run_auto_heal(ctx, threshold=98.0, state_file=state_path)

            self.assertEqual(result["status"], "noop")
            self.assertFalse(result["changed"])
            self.assertEqual(result["from_version"], "2.6.22")
            self.assertEqual(result["to_version"], "2.6.22")
            self.assertIsNone(result["apply_result"])

    def test_auto_heal_applies_when_version_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_auto_heal_app(root, "2.6.22", "c6285fea")
            state_path = root / ".cursor_zh_state" / "auto_heal_status.json"
            old_data_dir, _ = self._set_fake_auto_heal_data(root)

            try:
                write_json(
                    state_path,
                    {
                        "last_success": {"version": "2.6.21", "commit": "fea2f546"},
                    },
                )

                import cursor_zh.cli as mod

                with mock.patch.object(mod, "is_cursor_running", return_value=False):
                    result = run_auto_heal(
                        ctx,
                        threshold=98.0,
                        enable_dynamic_market=False,
                        state_file=state_path,
                    )

                self.assertEqual(result["status"], "applied")
                self.assertTrue(result["changed"])
                self.assertEqual(result["manifest_items"], 1)
                self.assertIsNotNone(result["apply_result"])
                self.assertIn("你好", read_text(ctx.app_path / "out" / "nls.messages.json"))

                state = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(state["last_success"]["version"], "2.6.22")
                self.assertEqual(state["last_success"]["commit"], "c6285fea")
            finally:
                import cursor_zh.cli as mod

                mod.DATA_DIR = old_data_dir

    def test_auto_heal_rejects_on_checksum_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_auto_heal_app(root, "2.6.22", "c6285fea")
            state_path = root / ".cursor_zh_state" / "auto_heal_status.json"
            old_data_dir, _ = self._set_fake_auto_heal_data(root)

            try:
                write_json(
                    state_path,
                    {
                        "last_success": {"version": "2.6.21", "commit": "fea2f546"},
                    },
                )

                import cursor_zh.cli as mod

                preview = {
                    "generated_at": "now",
                    "summary": {
                        "missing_files": 0,
                        "checksum_mismatch": 1,
                        "total_replacements_preview": 1,
                        "dynamic_market_patch": "anchor_missing",
                        "integrity_patch": "not_found",
                    },
                    "missing_files": [],
                    "checksum_mismatch": [str(ctx.app_path / "out" / "nls.messages.json")],
                    "details": [],
                    "dynamic_market_patch": {
                        "enabled": True,
                        "target_path": str(ctx.app_path / "out" / "vs" / "workbench" / "workbench.desktop.main.js"),
                        "applied": False,
                        "reason": "anchor_missing",
                        "anchor_ok": False,
                        "marker_present": False,
                        "phrase_pairs": 1,
                    },
                    "integrity_patch": {
                        "target_path": str(ctx.app_path / "out" / "vs" / "workbench" / "workbench.desktop.main.js"),
                        "applied": False,
                        "reason": "not_found",
                    },
                }

                with (
                    mock.patch.object(mod, "is_cursor_running", return_value=False),
                    mock.patch.object(mod, "dry_run_apply", return_value=preview),
                ):
                    result = run_auto_heal(
                        ctx,
                        threshold=98.0,
                        enable_dynamic_market=True,
                        state_file=state_path,
                    )

                self.assertEqual(result["status"], "blocked")
                self.assertEqual(result["failure_reason"], "checksum_mismatch")
                self.assertIsNone(result["apply_result"])
                self.assertIn('"Hello"', read_text(ctx.app_path / "out" / "nls.messages.json"))
            finally:
                import cursor_zh.cli as mod

                mod.DATA_DIR = old_data_dir

    def test_auto_heal_skips_when_cursor_is_running(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_auto_heal_app(root, "2.6.22", "c6285fea")
            state_path = root / ".cursor_zh_state" / "auto_heal_status.json"
            old_data_dir, _ = self._set_fake_auto_heal_data(root)

            try:
                write_json(
                    state_path,
                    {
                        "last_success": {"version": "2.6.21", "commit": "fea2f546"},
                    },
                )

                import cursor_zh.cli as mod

                with mock.patch.object(mod, "is_cursor_running", return_value=True):
                    result = run_auto_heal(
                        ctx,
                        threshold=98.0,
                        enable_dynamic_market=False,
                        state_file=state_path,
                    )

                self.assertEqual(result["status"], "pending")
                self.assertEqual(result["failure_reason"], "cursor_running")
                self.assertIsNone(result["apply_result"])
                self.assertIn('"Hello"', read_text(ctx.app_path / "out" / "nls.messages.json"))
            finally:
                import cursor_zh.cli as mod

                mod.DATA_DIR = old_data_dir

    def test_auto_heal_allows_missing_dynamic_market_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ctx = self._make_auto_heal_app(root, "2.6.22", "c6285fea", workbench_text="const demo = 1;\n")
            state_path = root / ".cursor_zh_state" / "auto_heal_status.json"
            old_data_dir, _ = self._set_fake_auto_heal_data(root)

            try:
                write_json(
                    state_path,
                    {
                        "last_success": {"version": "2.6.21", "commit": "fea2f546"},
                    },
                )

                import cursor_zh.cli as mod

                with mock.patch.object(mod, "is_cursor_running", return_value=False):
                    result = run_auto_heal(
                        ctx,
                        threshold=98.0,
                        enable_dynamic_market=True,
                        state_file=state_path,
                    )

                self.assertEqual(result["status"], "applied")
                self.assertEqual(result["dynamic_market_patch"]["reason"], "anchor_missing")
                self.assertIn("你好", read_text(ctx.app_path / "out" / "nls.messages.json"))
            finally:
                import cursor_zh.cli as mod

                mod.DATA_DIR = old_data_dir

    def test_build_auto_heal_launch_agent_plist_uses_repo_paths(self) -> None:
        plist_text = build_auto_heal_launch_agent_plist(
            label=AUTO_HEAL_LABEL,
            python_bin="/usr/bin/python3",
            repo_root=Path("/tmp/repo"),
            cursor_app=Path("/Applications/Cursor.app/Contents/Resources/app"),
            interval_minutes=10,
            threshold=98.0,
            enable_dynamic_market=True,
            state_file=Path("/tmp/repo/.cursor_zh_state/auto_heal_status.json"),
            stdout_log=Path("/tmp/repo/artifacts/logs/auto-heal.log"),
            stderr_log=Path("/tmp/repo/artifacts/logs/auto-heal.err.log"),
        )

        self.assertIn("<string>com.beta.cursor-zh.auto-heal</string>", plist_text)
        self.assertIn("<string>/bin/zsh</string>", plist_text)
        self.assertIn("<string>-lc</string>", plist_text)
        self.assertIn("cd /tmp/repo", plist_text)
        self.assertIn("export PYTHONPATH=/tmp/repo", plist_text)
        self.assertIn("exec /usr/bin/python3 -m cursor_zh auto-heal", plist_text)
        self.assertIn("<integer>600</integer>", plist_text)
        self.assertIn("<string>/tmp/repo/artifacts/logs/auto-heal.log</string>", plist_text)

    def test_build_parser_registers_auto_heal_commands(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()

        self.assertIn("auto-heal", help_text)
        self.assertIn("install-auto-heal", help_text)
        self.assertIn("uninstall-auto-heal", help_text)
        self.assertIn("status-auto-heal", help_text)

        auto_heal_args = parser.parse_args(
            [
                "auto-heal",
                "--cursor-app",
                "/Applications/Cursor.app/Contents/Resources/app",
                "--threshold",
                "97",
                "--state-file",
                "/tmp/auto-heal.json",
                "--log-file",
                "/tmp/auto-heal.log",
                "--enable-dynamic-market",
            ]
        )
        self.assertEqual(auto_heal_args.command, "auto-heal")
        self.assertEqual(auto_heal_args.cursor_app, "/Applications/Cursor.app/Contents/Resources/app")
        self.assertEqual(auto_heal_args.threshold, 97.0)
        self.assertEqual(auto_heal_args.state_file, "/tmp/auto-heal.json")
        self.assertEqual(auto_heal_args.log_file, "/tmp/auto-heal.log")
        self.assertTrue(auto_heal_args.enable_dynamic_market)

        install_args = parser.parse_args(
            [
                "install-auto-heal",
                "--cursor-app",
                "/Applications/Cursor.app/Contents/Resources/app",
                "--interval-minutes",
                "15",
                "--threshold",
                "96",
                "--state-file",
                "/tmp/state.json",
                "--stdout-log",
                "/tmp/out.log",
                "--stderr-log",
                "/tmp/err.log",
                "--enable-dynamic-market",
            ]
        )
        self.assertEqual(install_args.command, "install-auto-heal")
        self.assertEqual(install_args.interval_minutes, 15)
        self.assertEqual(install_args.threshold, 96.0)
        self.assertEqual(install_args.stdout_log, "/tmp/out.log")
        self.assertEqual(install_args.stderr_log, "/tmp/err.log")
        self.assertTrue(install_args.enable_dynamic_market)

        status_args = parser.parse_args(
            [
                "status-auto-heal",
                "--state-file",
                "/tmp/state.json",
                "--plist-path",
                "/tmp/demo.plist",
                "--stdout-log",
                "/tmp/out.log",
                "--stderr-log",
                "/tmp/err.log",
            ]
        )
        self.assertEqual(status_args.command, "status-auto-heal")
        self.assertEqual(status_args.plist_path, "/tmp/demo.plist")

        uninstall_args = parser.parse_args(["uninstall-auto-heal", "--plist-path", "/tmp/demo.plist"])
        self.assertEqual(uninstall_args.command, "uninstall-auto-heal")
        self.assertEqual(uninstall_args.plist_path, "/tmp/demo.plist")

    def test_build_skips_non_allowlisted_main_process_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            main_js = root / "Cursor.app" / "Contents" / "Resources" / "app" / "out" / "main.js"
            main_js.parent.mkdir(parents=True, exist_ok=True)
            main_js.write_text("const label = 'Browser';\n", encoding="utf-8")

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            try:
                fake_data = root / "data"
                (fake_data / "translations").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "translations" / "custom_phrases.json", {"Browser": "浏览器"})
                mod.DATA_DIR = fake_data

                manifest = run_build(
                    {
                        "cursor": {"app_path": str(main_js.parents[2]), "version": "2.5.25", "commit": "abcdef12"},
                        "files": [
                            {
                                "path": str(main_js),
                                "sha256": sha256_text(read_text(main_js)),
                                "tracked_hits": {"Browser": 1},
                            }
                        ],
                    }
                )
                self.assertEqual(manifest["summary"]["files_with_replacements"], 0)
                self.assertEqual(manifest["summary"]["replacement_items"], 0)
                self.assertEqual(manifest["files"], [])
            finally:
                mod.DATA_DIR = old_data_dir

    def test_build_and_apply_translates_tray_menu_labels_in_main_process_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            main_js = app / "out" / "main.js"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            main_js.parent.mkdir(parents=True, exist_ok=True)
            workbench.parent.mkdir(parents=True, exist_ok=True)
            main_js.write_text(
                'e.push({label:"No recent agents",enabled:!1});\n'
                'e.push({label:"Clear All Notifications"});\n'
                'e.push({label:"New Agent"});\n'
                'e.push({label:"Open Cursor"});\n'
                'e.push({label:"Settings"});\n'
                'e.push({label:"Quit"});\n',
                encoding="utf-8",
            )
            (app / "out" / "nls.messages.json").write_text("[]", encoding="utf-8")
            workbench.write_text("const noop = 1;\n", encoding="utf-8")
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"3.0.12"}\n', encoding="utf-8")

            report = run_scan(
                CursorContext(
                    app_path=app,
                    package_path=app / "package.json",
                    product_path=app / "product.json",
                    version="3.0.12",
                    commit="a80ff7df",
                    lang_pack_path=None,
                )
            )
            file_item = next(item for item in report["files"] if item["path"].endswith("out/main.js"))
            self.assertEqual(file_item["tracked_hits"]['label:"No recent agents"'], 1)
            self.assertEqual(file_item["tracked_hits"]['label:"Clear All Notifications"'], 1)
            self.assertEqual(file_item["tracked_hits"]['label:"New Agent"'], 1)
            self.assertEqual(file_item["tracked_hits"]['label:"Open Cursor"'], 1)
            self.assertEqual(file_item["tracked_hits"]['label:"Settings"'], 1)
            self.assertEqual(file_item["tracked_hits"]['label:"Quit"'], 1)

            manifest = run_build(report)
            result = apply_manifest(manifest, backup_root=root / "backup", force=False)
            self.assertGreaterEqual(result["changed_files_count"], 1)

            content = read_text(main_js)
            self.assertIn('label:"暂无最近智能体"', content)
            self.assertIn('label:"清除全部通知"', content)
            self.assertIn('label:"新建智能体"', content)
            self.assertIn('label:"打开 Cursor"', content)
            self.assertIn('label:"设置"', content)
            self.assertIn('label:"退出"', content)

    def test_scan_skips_identifier_like_js_phrases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                'const command = "$getTools"; const label = "Tools"; const setting = "workbench.externalBrowser";\n',
                encoding="utf-8",
            )
            (app / "out" / "nls.messages.json").write_text("{}", encoding="utf-8")
            (app / "product.json").write_text("{}\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"2.5.25"}\n', encoding="utf-8")

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            try:
                fake_data = root / "data"
                (fake_data / "translations").mkdir(parents=True, exist_ok=True)
                (fake_data / "coverage").mkdir(parents=True, exist_ok=True)
                write_json(
                    fake_data / "translations" / "custom_phrases.json",
                    {"Tools": "工具", '"Tools"': '"工具"', "Browser": "浏览器"},
                )
                write_json(fake_data / "coverage" / "core_phrases.json", [])
                mod.DATA_DIR = fake_data

                report = run_scan(
                    CursorContext(
                        app_path=app,
                        package_path=app / "package.json",
                        product_path=app / "product.json",
                        version="2.5.25",
                        commit="abcdef12",
                        lang_pack_path=None,
                    )
                )
                file_item = next(item for item in report["files"] if item["path"].endswith("workbench.desktop.main.js"))
                self.assertEqual(file_item["tracked_hits"], {'"Tools"': 1})
            finally:
                mod.DATA_DIR = old_data_dir

    def test_verify_exempt_keep_english_core_phrase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "f.txt"
            target.write_text('"Hooks"\n', encoding="utf-8")
            manifest = {
                "files": [
                    {
                        "path": str(target),
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [{"from": '"Hooks"', "to": '"Hooks"', "expected_hits": 1}],
                    }
                ]
            }

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            try:
                fake_data = root / "data"
                (fake_data / "coverage").mkdir(parents=True, exist_ok=True)
                (fake_data / "glossary").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "coverage" / "core_phrases.json", ['"Hooks"'])
                write_json(fake_data / "glossary" / "forbidden_terms.json", [])
                write_json(fake_data / "glossary" / "keep_english_terms.json", ["Hooks"])
                mod.DATA_DIR = fake_data

                report = run_verify(manifest, threshold=98.0)
                self.assertTrue(report["summary"]["pass"])
                self.assertEqual(report["summary"]["coverage_percent"], 100.0)
            finally:
                mod.DATA_DIR = old_data_dir

    def test_qa_placeholder_mismatch(self) -> None:
        manifest = {
            "files": [
                {
                    "path": "/tmp/demo",
                    "replacements": [
                        {"from": "Hello {0}", "to": "你好 {1}", "expected_hits": 1},
                    ],
                }
            ],
            "summary": {"replacement_items": 1, "untranslated_phrases_count": 0},
        }
        issues = collect_qa_issues(
            manifest=manifest,
            forced_terms={"Hello": "你好"},
            keep_terms=[],
            forbidden_terms=[],
        )
        self.assertTrue(any(item["type"] == "placeholder_mismatch" for item in issues["errors"]))

    def test_qa_keep_english_term(self) -> None:
        manifest = {
            "files": [
                {
                    "path": "/tmp/demo",
                    "replacements": [
                        {"from": "New Agent", "to": "新建助手", "expected_hits": 1},
                    ],
                }
            ],
            "summary": {"replacement_items": 1, "untranslated_phrases_count": 0},
        }
        issues = collect_qa_issues(
            manifest=manifest,
            forced_terms={},
            keep_terms=["Agent"],
            forbidden_terms=[],
        )
        self.assertTrue(any(item["type"] == "keep_english_term_missing" for item in issues["errors"]))

    def test_verify_allows_bilingual_keep_english_term(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "nls.messages.json"
            target.write_text('"智能体（Agents）"\n"云端智能体（Cloud Agents）"\n', encoding="utf-8")

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            try:
                fake_data = root / "data"
                (fake_data / "coverage").mkdir(parents=True, exist_ok=True)
                (fake_data / "glossary").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "coverage" / "core_phrases.json", ["Agents", "Cloud Agents"])
                write_json(fake_data / "glossary" / "forbidden_terms.json", [])
                write_json(fake_data / "glossary" / "keep_english_terms.json", ["Agents", "Cloud Agents"])
                mod.DATA_DIR = fake_data

                manifest = {
                    "files": [
                        {
                            "path": str(target),
                            "source_sha256": sha256_text(read_text(target)),
                            "replacements": [
                                {"from": "Agents", "to": "智能体（Agents）", "expected_hits": 1},
                                {"from": "Cloud Agents", "to": "云端智能体（Cloud Agents）", "expected_hits": 1},
                            ],
                        }
                    ]
                }

                report = run_verify(manifest, threshold=98.0)
                self.assertTrue(report["summary"]["pass"])
                self.assertEqual(report["summary"]["coverage_percent"], 100.0)
            finally:
                mod.DATA_DIR = old_data_dir

    def test_apply_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "a.txt"
            target.write_text("Manage Account\nNew Agent\n", encoding="utf-8")
            manifest = {
                "files": [
                    {
                        "path": str(target),
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [
                            {"from": "Manage Account", "to": "账号管理", "expected_hits": 1},
                            {"from": "New Agent", "to": "新建 Agent", "expected_hits": 1},
                        ],
                    }
                ]
            }
            preview = dry_run_apply(manifest, force=False)
            self.assertEqual(preview["summary"]["missing_files"], 0)
            self.assertEqual(preview["summary"]["checksum_mismatch"], 0)
            self.assertEqual(preview["summary"]["total_replacements_preview"], 2)

            backup_root = root / "backup"
            result = apply_manifest(manifest, backup_root=backup_root, force=False)
            self.assertEqual(result["changed_files_count"], 1)
            self.assertIn("账号管理", read_text(target))
            self.assertIn("新建 Agent", read_text(target))

            rollback_result = run_rollback(result)
            self.assertEqual(rollback_result["restored_files_count"], 1)
            self.assertIn("Manage Account", read_text(target))
            self.assertIn("New Agent", read_text(target))

    def test_build_and_apply_translates_empty_screen_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                'const a=\'hover:underline cursor-pointer opacity-80">Settings\';\n'
                'const b=\'<div>New project\';\n'
                'const c=\'<div class=empty-screen-view-all>View all (<!>)\';\n'
                'const d=\'<span>Recent projects</span>\';\n'
                'const e=\'text-description-foreground translate-x-[34px]">Sign in\';\n'
                'const f=\'<div>New Window\';\n'
                'const g=\'<div>Open project\';\n'
                'const h=\'<div>Clone repo\';\n'
                'const i=\'<div>Connect via SSH\';\n',
                encoding="utf-8",
            )
            (app / "out" / "nls.messages.json").write_text("[]", encoding="utf-8")
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"2.6.20"}\n', encoding="utf-8")

            report = run_scan(
                CursorContext(
                    app_path=app,
                    package_path=app / "package.json",
                    product_path=app / "product.json",
                    version="2.6.20",
                    commit="b29eb4ee",
                    lang_pack_path=None,
                )
            )
            file_item = next(item for item in report["files"] if item["path"].endswith("workbench.desktop.main.js"))
            self.assertEqual(file_item["tracked_hits"]["<div>New project"], 1)
            self.assertEqual(file_item["tracked_hits"]["<span>Recent projects</span>"], 1)
            self.assertEqual(
                file_item["tracked_hits"]["<div class=empty-screen-view-all>View all (<!>)"],
                1,
            )
            self.assertEqual(file_item["tracked_hits"]["<div>Open project"], 1)
            self.assertEqual(file_item["tracked_hits"]["<div>Clone repo"], 1)
            self.assertEqual(file_item["tracked_hits"]["<div>Connect via SSH"], 1)
            self.assertEqual(
                file_item["tracked_hits"]["hover:underline cursor-pointer opacity-80\">Settings"],
                1,
            )
            self.assertEqual(
                file_item["tracked_hits"]["text-description-foreground translate-x-[34px]\">Sign in"],
                1,
            )
            self.assertEqual(file_item["tracked_hits"]["<div>New Window"], 1)

            manifest = run_build(report)
            result = apply_manifest(manifest, backup_root=root / "backup", force=False)
            self.assertGreaterEqual(result["changed_files_count"], 1)

            content = read_text(workbench)
            self.assertIn("设置", content)
            self.assertIn("新建项目", content)
            self.assertIn("打开项目", content)
            self.assertIn("克隆仓库", content)
            self.assertIn("通过 SSH 连接", content)
            self.assertIn("查看全部（<!>）", content)
            self.assertIn("最近项目", content)
            self.assertIn("登录", content)
            self.assertIn("新建窗口", content)

    def test_build_and_apply_translates_settings_layout_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                'const a="Manage Account";\n'
                'const b="Manage your account and billing";\n'
                'const c="Sync layouts across windows";\n'
                'const d="Keyboard Shortcuts";\n'
                'const e="Import Settings from VS Code";\n'
                'const f="Auto-hide editor when empty";\n'
                'const g="When all editors are closed, hide the editor area and maximize chat";\n',
                encoding="utf-8",
            )
            (app / "out" / "nls.messages.json").write_text("[]", encoding="utf-8")
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"2.6.20"}\n', encoding="utf-8")

            report = run_scan(
                CursorContext(
                    app_path=app,
                    package_path=app / "package.json",
                    product_path=app / "product.json",
                    version="2.6.20",
                    commit="b29eb4ee",
                    lang_pack_path=None,
                )
            )
            file_item = next(item for item in report["files"] if item["path"].endswith("workbench.desktop.main.js"))
            self.assertEqual(file_item["tracked_hits"]["Manage Account"], 1)
            self.assertEqual(file_item["tracked_hits"]["Manage your account and billing"], 1)
            self.assertEqual(file_item["tracked_hits"]["Sync layouts across windows"], 1)
            self.assertEqual(file_item["tracked_hits"]["Keyboard Shortcuts"], 1)
            self.assertEqual(file_item["tracked_hits"]["Import Settings from VS Code"], 1)
            self.assertEqual(file_item["tracked_hits"]["Auto-hide editor when empty"], 1)
            self.assertEqual(
                file_item["tracked_hits"]["When all editors are closed, hide the editor area and maximize chat"],
                1,
            )

            manifest = run_build(report)
            result = apply_manifest(manifest, backup_root=root / "backup", force=False)
            self.assertGreaterEqual(result["changed_files_count"], 1)

            content = read_text(workbench)
            self.assertIn("账号管理", content)
            self.assertIn("管理账号与计费", content)
            self.assertIn("跨窗口同步布局", content)
            self.assertIn("快捷键", content)
            self.assertIn("从 VS Code 导入设置", content)
            self.assertIn("编辑器为空时自动隐藏", content)
            self.assertIn("当所有编辑器关闭时，隐藏编辑器区域并最大化聊天", content)

    def test_build_and_apply_translates_common_menu_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                'const a="Settings";\n'
                'const b="Quit";\n'
                'const c="Clear All Notifications";\n'
                'const d="Close";\n'
                'const e="Cancel";\n',
                encoding="utf-8",
            )
            write_json(
                app / "out" / "nls.messages.json",
                [
                    "Undo",
                    "Redo",
                    "Cut",
                    "Copy",
                    "Paste",
                    "Select All",
                    "&&Undo",
                    "&&Redo",
                    "&&Cut",
                    "&&Copy",
                    "&&Paste",
                    "&&Cancel",
                    "&&Close",
                    "&&Select All",
                ],
            )
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"3.0.12"}\n', encoding="utf-8")

            report = run_scan(
                CursorContext(
                    app_path=app,
                    package_path=app / "package.json",
                    product_path=app / "product.json",
                    version="3.0.12",
                    commit="a80ff7df",
                    lang_pack_path=None,
                )
            )
            nls_item = next(item for item in report["files"] if item["path"].endswith("nls.messages.json"))
            workbench_item = next(item for item in report["files"] if item["path"].endswith("workbench.desktop.main.js"))
            self.assertEqual(nls_item["tracked_hits"]['"Undo"'], 1)
            self.assertEqual(nls_item["tracked_hits"]["&&Copy"], 1)
            self.assertEqual(nls_item["tracked_hits"]["&&Select All"], 1)
            self.assertEqual(workbench_item["tracked_hits"]['"Settings"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['"Clear All Notifications"'], 1)

            manifest = run_build(report)
            result = apply_manifest(manifest, backup_root=root / "backup", force=False)
            self.assertGreaterEqual(result["changed_files_count"], 1)

            nls_content = read_text(app / "out" / "nls.messages.json")
            workbench_content = read_text(workbench)
            self.assertIn('"撤销"', nls_content)
            self.assertIn('"重做"', nls_content)
            self.assertIn('"剪切"', nls_content)
            self.assertIn('"复制"', nls_content)
            self.assertIn('"粘贴"', nls_content)
            self.assertIn('"全选"', nls_content)
            self.assertIn("&&撤销", nls_content)
            self.assertIn("&&复制", nls_content)
            self.assertIn("&&关闭", nls_content)
            self.assertIn('"设置"', workbench_content)
            self.assertIn('"退出"', workbench_content)
            self.assertIn('"清除全部通知"', workbench_content)
            self.assertIn('"关闭"', workbench_content)
            self.assertIn('"取消"', workbench_content)

    def test_build_and_apply_translates_appearance_menu_strings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                'const a={label:"Appearance"};\n'
                'const b={label:"Help"};\n'
                'const c={title:"Log Out"};\n'
                'const d=[{mode:"light",label:"Light"},{mode:"dark",label:"Dark"},{mode:"system",label:"System"}];\n'
                'const e={label:"High Contrast"};\n',
                encoding="utf-8",
            )
            write_json(
                app / "out" / "nls.messages.json",
                [
                    "Appearance",
                    "Help",
                    "System",
                    "Light",
                    "Dark",
                    "High Contrast",
                    "&&Appearance",
                    "&&Help",
                ],
            )
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")
            (app / "package.json").write_text('{"version":"3.0.12"}\n', encoding="utf-8")

            report = run_scan(
                CursorContext(
                    app_path=app,
                    package_path=app / "package.json",
                    product_path=app / "product.json",
                    version="3.0.12",
                    commit="a80ff7df",
                    lang_pack_path=None,
                )
            )
            nls_item = next(item for item in report["files"] if item["path"].endswith("nls.messages.json"))
            workbench_item = next(item for item in report["files"] if item["path"].endswith("workbench.desktop.main.js"))
            self.assertEqual(nls_item["tracked_hits"]['"Appearance"'], 1)
            self.assertEqual(nls_item["tracked_hits"]["&&Appearance"], 1)
            self.assertEqual(nls_item["tracked_hits"]['"Help"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"Appearance"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"Help"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['"Log Out"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"System"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"Light"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"Dark"'], 1)
            self.assertEqual(workbench_item["tracked_hits"]['label:"High Contrast"'], 1)

            manifest = run_build(report)
            result = apply_manifest(manifest, backup_root=root / "backup", force=False)
            self.assertGreaterEqual(result["changed_files_count"], 1)

            nls_content = read_text(app / "out" / "nls.messages.json")
            workbench_content = read_text(workbench)
            self.assertIn('"外观"', nls_content)
            self.assertIn('"帮助"', nls_content)
            self.assertIn('"跟随系统"', nls_content)
            self.assertIn('"浅色"', nls_content)
            self.assertIn('"深色"', nls_content)
            self.assertIn('"高对比度"', nls_content)
            self.assertIn("&&外观", nls_content)
            self.assertIn("&&帮助", nls_content)
            self.assertIn('label:"外观"', workbench_content)
            self.assertIn('label:"帮助"', workbench_content)
            self.assertIn('"退出登录"', workbench_content)
            self.assertIn('label:"跟随系统"', workbench_content)
            self.assertIn('label:"浅色"', workbench_content)
            self.assertIn('label:"深色"', workbench_content)
            self.assertIn('label:"高对比度"', workbench_content)

    def test_scan_reports_dynamic_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            (app / "out" / "vs" / "workbench").mkdir(parents=True, exist_ok=True)
            (app / "extensions" / "cursor-demo").mkdir(parents=True, exist_ok=True)
            (app / "out" / "main.js").write_text('const s = "Past Chats";\n', encoding="utf-8")
            (app / "out" / "nls.messages.json").write_text("{}", encoding="utf-8")
            (app / "out" / "vs" / "workbench" / "workbench.desktop.main.js").write_text(
                "function x(){ return fetch('/marketplace'); }\n",
                encoding="utf-8",
            )
            write_json(
                app / "extensions" / "cursor-demo" / "package.json",
                {
                    "name": "cursor-demo",
                    "description": "Supercharge Git within VS Code",
                    "contributes": {"commands": [{"command": "cursor.demo.run", "title": "Run Demo"}]},
                },
            )

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            try:
                fake_data = root / "data"
                (fake_data / "translations").mkdir(parents=True, exist_ok=True)
                (fake_data / "coverage").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "translations" / "custom_phrases.json", {"Past Chats": "历史聊天"})
                write_json(fake_data / "coverage" / "core_phrases.json", [])
                mod.DATA_DIR = fake_data

                report = run_scan(
                    CursorContext(
                        app_path=app,
                        package_path=app / "package.json",
                        product_path=app / "product.json",
                        version="2.5.25",
                        commit="abcdef12",
                        lang_pack_path=None,
                    )
                )
                self.assertEqual(report["summary"]["static_total_phrase_hits"], 0)
                self.assertGreater(report["summary"]["dynamic_candidate_literals"], 0)
                ext_file = next(item for item in report["files"] if item["path"].endswith("cursor-demo/package.json"))
                self.assertIn("Supercharge Git within VS Code", ext_file["sample_dynamic_literals"])
            finally:
                mod.DATA_DIR = old_data_dir

    def test_apply_dynamic_market_patch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                "function demo(){ return fetch('/marketplace/plugins'); }\n",
                encoding="utf-8",
            )
            manifest = {
                "cursor": {"app_path": str(app)},
                "files": [],
            }
            backup_root = root / "backup"

            result = apply_manifest(manifest, backup_root=backup_root, force=False, enable_dynamic_market=True)
            self.assertEqual(result["changed_files_count"], 1)
            self.assertTrue(result["dynamic_market_patch"]["applied"])
            self.assertIn("CURSOR_ZH_DYNAMIC_MARKET_BEGIN", read_text(workbench))

            rollback_result = run_rollback(result)
            self.assertEqual(rollback_result["restored_files_count"], 1)
            self.assertNotIn("CURSOR_ZH_DYNAMIC_MARKET_BEGIN", read_text(workbench))

    def test_dynamic_market_patch_anchor_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text("console.log('no network hook');\n", encoding="utf-8")
            manifest = {"cursor": {"app_path": str(app)}, "files": []}

            result = apply_manifest(
                manifest,
                backup_root=root / "backup",
                force=False,
                enable_dynamic_market=True,
            )
            self.assertEqual(result["changed_files_count"], 0)
            self.assertFalse(result["dynamic_market_patch"]["applied"])
            self.assertEqual(result["dynamic_market_patch"]["reason"], "anchor_missing")

    def test_apply_dynamic_market_patch_updates_existing_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                "function demo(){ return fetch('/marketplace/plugins'); }\n"
                "/* CURSOR_ZH_DYNAMIC_MARKET_BEGIN v1 */\nold block\n/* CURSOR_ZH_DYNAMIC_MARKET_END v1 */\n",
                encoding="utf-8",
            )
            manifest = {"cursor": {"app_path": str(app)}, "files": []}

            result = apply_manifest(
                manifest,
                backup_root=root / "backup",
                force=False,
                enable_dynamic_market=True,
            )
            self.assertTrue(result["dynamic_market_patch"]["applied"])
            self.assertEqual(result["dynamic_market_patch"]["reason"], "updated")
            content = read_text(workbench)
            self.assertNotIn("old block", content)
            self.assertIn("MARKET_URL_SIGNS", content)

    def test_apply_patches_integrity_without_dynamic_market(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text(
                "foo"
                "async _isPure(){const e=this.productService.checksums||{};await this.lifecycleService.when(4);"
                "const t=await Promise.all(Object.keys(e).map(r=>this._resolve(r,e[r])));let i=!0;"
                "for(let r=0,s=t.length;r<s;r++)if(!t[r].isPure){i=!1;break}return{isPure:i,proof:t}}"
                "bar\n",
                encoding="utf-8",
            )
            product_path = app / "product.json"
            product_path.write_text(
                json.dumps(
                    {
                        "nameShort": "Cursor",
                        "checksums": {
                            "vs/workbench/workbench.desktop.main.js": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
                        },
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            manifest = {"cursor": {"app_path": str(app)}, "files": []}

            result = apply_manifest(manifest, backup_root=root / "backup", force=False, enable_dynamic_market=False)

            self.assertEqual(result["dynamic_market_patch"]["reason"], "disabled")
            self.assertTrue(result["integrity_patch"]["applied"])
            self.assertEqual(result["integrity_patch"]["reason"], "applied")
            self.assertIn("async _isPure(){return{isPure:!0,proof:[]}}", read_text(workbench))
            after = json.loads(product_path.read_text(encoding="utf-8"))
            self.assertEqual(
                after["checksums"]["vs/workbench/workbench.desktop.main.js"],
                sha256_file_base64(workbench),
            )

    def test_disable_integrity_service_rewrites_runtime_check(self) -> None:
        original = (
            "foo"
            "async _isPure(){const e=this.productService.checksums||{};await this.lifecycleService.when(4);"
            "const t=await Promise.all(Object.keys(e).map(r=>this._resolve(r,e[r])));let i=!0;"
            "for(let r=0,s=t.length;r<s;r++)if(!t[r].isPure){i=!1;break}return{isPure:i,proof:t}}"
            "bar"
        )
        updated, changed = disable_integrity_service(original)

        self.assertTrue(changed)
        self.assertIn("async _isPure(){return{isPure:!0,proof:[]}}", updated)
        self.assertNotIn("Promise.all(Object.keys(e).map", updated)

    def test_upsert_dynamic_market_patch_replaces_existing_block(self) -> None:
        original = "\n".join(
            [
                "const a = 1;",
                "/* CURSOR_ZH_DYNAMIC_MARKET_BEGIN v1 */",
                "old block",
                "/* CURSOR_ZH_DYNAMIC_MARKET_END v1 */",
                "const b = 2;",
            ]
        )
        updated, changed = upsert_dynamic_market_patch(
            original,
            "/* CURSOR_ZH_DYNAMIC_MARKET_BEGIN v1 */\nnew block\n/* CURSOR_ZH_DYNAMIC_MARKET_END v1 */",
        )
        self.assertTrue(changed)
        self.assertNotIn("old block", updated)
        self.assertIn("new block", updated)
        self.assertIn("const b = 2;", updated)

    def test_apply_syncs_product_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            workbench = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            workbench.parent.mkdir(parents=True, exist_ok=True)
            workbench.write_text("function demo(){ return fetch('/marketplace/plugins'); }\n", encoding="utf-8")
            product_path = app / "product.json"
            product = {
                "nameShort": "Cursor",
                "checksums": {"vs/workbench/workbench.desktop.main.js": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="},
            }
            product_path.write_text(json.dumps(product, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            manifest = {
                "cursor": {"app_path": str(app)},
                "files": [],
            }

            result = apply_manifest(manifest, backup_root=root / "backup", force=False, enable_dynamic_market=True)
            self.assertEqual(result["checksum_sync"]["reason"], "updated")
            self.assertGreaterEqual(result["checksum_sync"]["updated"], 1)

            after = json.loads(product_path.read_text(encoding="utf-8"))
            self.assertEqual(
                after["checksums"]["vs/workbench/workbench.desktop.main.js"],
                sha256_file_base64(workbench),
            )

            rollback_result = run_rollback(result)
            self.assertGreaterEqual(rollback_result["restored_files_count"], 1)
            restored = json.loads(product_path.read_text(encoding="utf-8"))
            self.assertEqual(
                restored["checksums"]["vs/workbench/workbench.desktop.main.js"],
                "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=",
            )

    def test_collect_product_checksum_updates_only_touched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            wb = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            css = app / "out" / "vs" / "workbench" / "workbench.desktop.main.css"
            wb.parent.mkdir(parents=True, exist_ok=True)
            wb.write_text("aaa", encoding="utf-8")
            css.write_text("bbb", encoding="utf-8")
            product = {
                "checksums": {
                    "vs/workbench/workbench.desktop.main.js": "old-a",
                    "vs/workbench/workbench.desktop.main.css": "old-b",
                }
            }
            (app / "product.json").write_text(json.dumps(product) + "\n", encoding="utf-8")

            updates = collect_product_checksum_updates(app, touched_paths=[wb])
            self.assertIn("vs/workbench/workbench.desktop.main.js", updates)
            self.assertNotIn("vs/workbench/workbench.desktop.main.css", updates)

    def test_collect_product_checksum_updates_adds_missing_keys_for_touched_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            nls = app / "out" / "nls.messages.json"
            ext = app / "extensions" / "cursor-browser-automation" / "package.json"
            nls.parent.mkdir(parents=True, exist_ok=True)
            ext.parent.mkdir(parents=True, exist_ok=True)
            nls.write_text('["已汉化"]\n', encoding="utf-8")
            ext.write_text('{"displayName":"浏览器自动化"}\n', encoding="utf-8")
            (app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")

            updates = collect_product_checksum_updates(app, touched_paths=[nls, ext])

            self.assertEqual(updates["nls.messages.json"], sha256_file_base64(nls))
            self.assertEqual(
                updates["extensions/cursor-browser-automation/package.json"],
                sha256_file_base64(ext),
            )

    def test_apply_syncs_all_product_checksums(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            wb = app / "out" / "vs" / "workbench" / "workbench.desktop.main.js"
            css = app / "out" / "vs" / "workbench" / "workbench.desktop.main.css"
            wb.parent.mkdir(parents=True, exist_ok=True)
            wb.write_text("function demo(){ return fetch('/marketplace/plugins'); }\n", encoding="utf-8")
            css.write_text("body { color: white; }\n", encoding="utf-8")
            product_path = app / "product.json"
            product = {
                "nameShort": "Cursor",
                "checksums": {
                    "vs/workbench/workbench.desktop.main.js": "old-js",
                    "vs/workbench/workbench.desktop.main.css": "old-css",
                },
            }
            product_path.write_text(json.dumps(product, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

            manifest = {"cursor": {"app_path": str(app)}, "files": []}
            result = apply_manifest(manifest, backup_root=root / "backup", force=False, enable_dynamic_market=True)

            self.assertEqual(result["checksum_sync"]["reason"], "updated")
            self.assertEqual(result["checksum_sync"]["updated"], 2)
            self.assertIn("vs/workbench/workbench.desktop.main.js", result["checksum_sync"]["updated_keys"])
            self.assertIn("vs/workbench/workbench.desktop.main.css", result["checksum_sync"]["updated_keys"])

            after = json.loads(product_path.read_text(encoding="utf-8"))
            self.assertEqual(
                after["checksums"]["vs/workbench/workbench.desktop.main.js"],
                sha256_file_base64(wb),
            )
            self.assertEqual(
                after["checksums"]["vs/workbench/workbench.desktop.main.css"],
                sha256_file_base64(css),
            )

    def test_export_store_extension_generates_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            ext = app / "extensions" / "cursor-demo"
            ext.mkdir(parents=True, exist_ok=True)
            write_json(ext / "package.json", {"name": "cursor-demo", "publisher": "anysphere", "version": "0.0.1"})
            write_json(
                ext / "package.nls.json",
                {
                    "displayName": "AI Completions",
                    "description": "Get completions from a code language model.",
                },
            )

            lang_pack = root / "lang-pack"
            lang_pack.mkdir(parents=True, exist_ok=True)
            write_json(lang_pack / "package.json", {"version": "1.105.0"})

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            old_overrides_path = mod.STORE_EXTENSION_OVERRIDES_PATH
            old_store_artifacts_dir = mod.STORE_EXTENSION_ARTIFACTS_DIR
            try:
                fake_data = root / "data"
                (fake_data / "translations").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "translations" / "custom_phrases.json", {})
                write_json(
                    fake_data / "translations" / "store_extension_overrides.json",
                    {
                        "anysphere.cursor-demo": {
                            "displayName": "AI 补全",
                            "description": "从代码语言模型获取补全建议。",
                        }
                    },
                )
                mod.DATA_DIR = fake_data
                mod.STORE_EXTENSION_OVERRIDES_PATH = fake_data / "translations" / "store_extension_overrides.json"
                mod.STORE_EXTENSION_ARTIFACTS_DIR = root / "artifacts" / "store_extension"

                output_dir = root / "beta-cursor-hanhua"
                report = run_export_store_extension(
                    CursorContext(
                        app_path=app,
                        package_path=app / "package.json",
                        product_path=app / "product.json",
                        version="2.6.18",
                        commit="68fbec5a",
                        lang_pack_path=lang_pack,
                    ),
                    output_dir=output_dir,
                    publisher="beta-cursor",
                    version="0.1.0",
                )

                self.assertEqual(report["summary"]["localized_extensions"], 1)
                self.assertEqual(report["summary"]["blocked_extensions"], 0)
                package_json = json.loads((output_dir / "package.json").read_text(encoding="utf-8"))
                self.assertEqual(package_json["displayName"], "Beta Cursor 私有扩展汉化覆盖层（实验）")
                self.assertEqual(package_json["name"], "beta-cursor-hanhua")
                self.assertEqual(package_json["version"], "0.1.0")
                self.assertNotIn("extensionDependencies", package_json)
                self.assertEqual(package_json["icon"], "media/icon.png")
                self.assertTrue((output_dir / "media" / "icon.png").exists())
                self.assertTrue((output_dir / "LICENSE").exists())
                self.assertTrue((output_dir / "scripts" / "package-openvsx.sh").exists())
                self.assertTrue((output_dir / "scripts" / "publish-openvsx.sh").exists())
                readme = (output_dir / "README.md").read_text(encoding="utf-8")
                self.assertIn("当前导出基于 Cursor `2.6.18`", readme)
                self.assertIn("`--version 0.1.0`", readme)
                self.assertIn("这不是本扩展的前置条件", readme)
                changelog = (output_dir / "CHANGELOG.md").read_text(encoding="utf-8")
                self.assertIn("## 0.1.0", changelog)
                self.assertIn("适配 Cursor 2.6.18", changelog)
                self.assertIn("不依赖官方简体中文语言包作为安装前提", changelog)

                translation = json.loads(
                    (output_dir / "translations" / "extensions" / "anysphere.cursor-demo.i18n.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(translation["contents"]["package"]["displayName"], "AI 补全")
                self.assertEqual(
                    translation["contents"]["package"]["description"],
                    "从代码语言模型获取补全建议。",
                )
            finally:
                mod.DATA_DIR = old_data_dir
                mod.STORE_EXTENSION_OVERRIDES_PATH = old_overrides_path
                mod.STORE_EXTENSION_ARTIFACTS_DIR = old_store_artifacts_dir

    def test_export_store_extension_reports_blocked_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"

            exportable = app / "extensions" / "cursor-exportable"
            exportable.mkdir(parents=True, exist_ok=True)
            write_json(exportable / "package.json", {"name": "cursor-exportable", "publisher": "anysphere"})
            write_json(exportable / "package.nls.json", {"displayName": "AI Completions"})

            blocked = app / "extensions" / "cursor-blocked"
            blocked.mkdir(parents=True, exist_ok=True)
            write_json(blocked / "package.json", {"name": "cursor-blocked", "publisher": "anysphere"})

            lang_pack = root / "lang-pack"
            lang_pack.mkdir(parents=True, exist_ok=True)
            write_json(lang_pack / "package.json", {"version": "1.105.0"})

            import cursor_zh.cli as mod

            old_data_dir = mod.DATA_DIR
            old_overrides_path = mod.STORE_EXTENSION_OVERRIDES_PATH
            old_store_artifacts_dir = mod.STORE_EXTENSION_ARTIFACTS_DIR
            try:
                fake_data = root / "data"
                (fake_data / "translations").mkdir(parents=True, exist_ok=True)
                write_json(fake_data / "translations" / "custom_phrases.json", {"AI Completions": "AI 补全"})
                write_json(fake_data / "translations" / "store_extension_overrides.json", {})
                mod.DATA_DIR = fake_data
                mod.STORE_EXTENSION_OVERRIDES_PATH = fake_data / "translations" / "store_extension_overrides.json"
                mod.STORE_EXTENSION_ARTIFACTS_DIR = root / "artifacts" / "store_extension"

                report = run_export_store_extension(
                    CursorContext(
                        app_path=app,
                        package_path=app / "package.json",
                        product_path=app / "product.json",
                        version="2.6.18",
                        commit="68fbec5a",
                        lang_pack_path=lang_pack,
                    ),
                    output_dir=root / "beta-cursor-hanhua",
                )

                self.assertEqual(report["summary"]["localized_extensions"], 1)
                self.assertEqual(report["summary"]["blocked_extensions"], 1)
                self.assertEqual(report["blocked_targets"][0]["extension_id"], "anysphere.cursor-blocked")
                readme = (root / "beta-cursor-hanhua" / "README.md").read_text(encoding="utf-8")
                self.assertIn("当前导出基于 Cursor `2.6.18`", readme)
                self.assertIn("`--version 0.1.0`", readme)
            finally:
                mod.DATA_DIR = old_data_dir
                mod.STORE_EXTENSION_OVERRIDES_PATH = old_overrides_path
                mod.STORE_EXTENSION_ARTIFACTS_DIR = old_store_artifacts_dir

    def test_apply_uses_target_rel_path_with_cursor_app_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src_app = root / "Source.app" / "Contents" / "Resources" / "app"
            dst_app = root / "Target.app" / "Contents" / "Resources" / "app"
            src_file = src_app / "out" / "nls.messages.json"
            dst_file = dst_app / "out" / "nls.messages.json"
            src_file.parent.mkdir(parents=True, exist_ok=True)
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.write_text('"Hello"\n', encoding="utf-8")
            dst_file.write_text('"Hello"\n', encoding="utf-8")
            (dst_app / "product.json").write_text(json.dumps({"checksums": {}}) + "\n", encoding="utf-8")

            manifest = {
                "cursor": {"app_path": str(src_app), "version": "2.6.18", "commit": "68fbec5a"},
                "files": [
                    {
                        "path": str(src_file),
                        "target_rel_path": "out/nls.messages.json",
                        "source_sha256": sha256_text(read_text(src_file)),
                        "replacements": [{"from": '"Hello"', "to": '"你好"', "expected_hits": 1}],
                    }
                ],
            }

            result = apply_manifest(
                manifest,
                backup_root=root / "backup",
                force=False,
                cursor_app_override=dst_app,
            )

            self.assertEqual(result["changed_files_count"], 2)
            self.assertIn('"你好"', read_text(dst_file))
            self.assertIn('"Hello"', read_text(src_file))

    def test_export_local_bundle_creates_portable_installer(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            target = app / "out" / "nls.messages.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('"Hello"\n', encoding="utf-8")

            manifest = {
                "manifest_version": 1,
                "cursor": {"app_path": str(app), "version": "2.6.18", "commit": "68fbec5a"},
                "files": [
                    {
                        "path": str(target),
                        "target_rel_path": "out/nls.messages.json",
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [{"from": '"Hello"', "to": '"你好"', "expected_hits": 1}],
                    }
                ],
            }

            bundle_dir = root / "Beta-Cursor-全面汉化-2.6.18-68fbec5a"
            report = run_export_local_bundle(manifest, output_dir=bundle_dir, enable_dynamic_market=True)

            portable_manifest = json.loads((bundle_dir / "payload" / "patch_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(portable_manifest["files"][0]["target_rel_path"], "out/nls.messages.json")
            self.assertEqual(portable_manifest["files"][0]["path"], "out/nls.messages.json")
            self.assertIsNone(portable_manifest["cursor"]["app_path"])
            self.assertIsNone(portable_manifest["cursor"].get("lang_pack_path"))
            self.assertEqual(report["bundle_name"], "Beta-Cursor-全面汉化-2.6.18-68fbec5a")
            self.assertTrue((bundle_dir / "macOS" / "安装.command").exists())
            self.assertTrue((bundle_dir / "macOS" / "回滚.command").exists())
            self.assertTrue((bundle_dir / "Windows" / "安装.bat").exists())
            self.assertTrue((bundle_dir / "Windows" / "回滚.bat").exists())
            self.assertTrue((bundle_dir / "使用说明.txt").exists())
            self.assertIsNone(report["archive_path"])
            self.assertFalse((root / "Beta-Cursor-全面汉化-2.6.18-68fbec5a.zip").exists())
            readme = (bundle_dir / "使用说明.txt").read_text(encoding="utf-8")
            self.assertIn("macOS/安装.command", readme)
            self.assertIn("Windows/安装.bat", readme)
            self.assertIn("不会下载、复制或安装第二个 Cursor", readme)
            self.assertIn("Python 3", readme)
            self.assertIn("payload/artifacts/backups/", readme)

    def test_export_local_bundle_removes_stale_zip_when_not_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            target = app / "out" / "nls.messages.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('"Hello"\n', encoding="utf-8")

            manifest = {
                "manifest_version": 1,
                "cursor": {"app_path": str(app), "version": "2.6.18", "commit": "68fbec5a"},
                "files": [
                    {
                        "path": str(target),
                        "target_rel_path": "out/nls.messages.json",
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [{"from": '"Hello"', "to": '"你好"', "expected_hits": 1}],
                    }
                ],
            }

            bundle_dir = root / "bundle-2.6.18"
            stale_zip = Path(str(bundle_dir) + ".zip")
            stale_zip.write_text("old", encoding="utf-8")

            run_export_local_bundle(manifest, output_dir=bundle_dir, enable_dynamic_market=False)

            self.assertFalse(stale_zip.exists())

    def test_export_local_bundle_windows_scripts_use_relative_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            target = app / "out" / "nls.messages.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('"Hello"\n', encoding="utf-8")

            manifest = {
                "manifest_version": 1,
                "cursor": {"app_path": str(app), "version": "2.6.18", "commit": "68fbec5a"},
                "files": [
                    {
                        "path": str(target),
                        "target_rel_path": "out/nls.messages.json",
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [{"from": '"Hello"', "to": '"你好"', "expected_hits": 1}],
                    }
                ],
            }

            bundle_dir = root / "bundle-win"
            run_export_local_bundle(manifest, output_dir=bundle_dir, enable_dynamic_market=True)

            install_bat = (bundle_dir / "Windows" / "安装.bat").read_text(encoding="utf-8")
            rollback_bat = (bundle_dir / "Windows" / "回滚.bat").read_text(encoding="utf-8")

            self.assertIn('for %%I in ("%SCRIPT_DIR%..") do set "ROOT_DIR=%%~fI"', install_bat)
            self.assertIn('set "PAYLOAD_DIR=%ROOT_DIR%\\payload"', install_bat)
            self.assertIn("-m cursor_zh apply", install_bat)
            self.assertIn("--enable-dynamic-market", install_bat)
            self.assertIn('set "PAYLOAD_DIR=%ROOT_DIR%\\payload"', rollback_bat)
            self.assertIn("-m cursor_zh rollback", rollback_bat)

    def test_export_local_bundle_macos_scripts_install_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app = root / "Cursor.app" / "Contents" / "Resources" / "app"
            target = app / "out" / "nls.messages.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('"Hello"\n', encoding="utf-8")
            write_json(app / "package.json", {"version": "2.6.18"})
            write_json(app / "product.json", {"commit": "68fbec5a", "checksums": {}})

            manifest = {
                "manifest_version": 1,
                "cursor": {
                    "app_path": str(app),
                    "version": "2.6.18",
                    "commit": "68fbec5a",
                    "lang_pack_path": "/Users/demo/.cursor/extensions/ms-ceintl.vscode-language-pack-zh-hans-1.105.0-universal",
                },
                "files": [
                    {
                        "path": str(target),
                        "target_rel_path": "out/nls.messages.json",
                        "source_sha256": sha256_text(read_text(target)),
                        "replacements": [{"from": '"Hello"', "to": '"你好"', "expected_hits": 1}],
                    }
                ],
            }

            bundle_dir = root / "bundle-smoke"
            run_export_local_bundle(manifest, output_dir=bundle_dir, enable_dynamic_market=False)

            install_script = bundle_dir / "macOS" / "安装.command"
            rollback_script = bundle_dir / "macOS" / "回滚.command"

            install = subprocess.run(
                ["bash", str(install_script), str(app)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(install.returncode, 0, install.stderr)
            self.assertIn("只会修改现有安装", install.stdout)
            self.assertIn("预计变更文件=1", install.stdout)
            self.assertIn('"你好"', read_text(target))
            last_apply = bundle_dir / "payload" / ".cursor_zh_state" / "last_apply.json"
            self.assertTrue(last_apply.exists())

            rollback = subprocess.run(
                ["bash", str(rollback_script)],
                cwd=root,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(rollback.returncode, 0, rollback.stderr)
            self.assertIn('"Hello"', read_text(target))


if __name__ == "__main__":
    unittest.main()
