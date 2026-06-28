"""Static startup/menu contracts.

These tests parse main.py without importing PySide6. They catch missing
MainWindow methods referenced by menu actions before the user sees a startup
crash.
"""

from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StartupMenuContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        self.main_window = next(
            node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow"
        )
        self.methods = {node.name for node in self.main_window.body if isinstance(node, ast.FunctionDef)}

    def test_menu_action_method_targets_exist(self) -> None:
        build_menus = next(
            node for node in self.main_window.body if isinstance(node, ast.FunctionDef) and node.name == "_build_menus"
        )
        missing: list[str] = []
        for node in ast.walk(build_menus):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "make_action":
                continue
            if len(node.args) < 2:
                continue
            target = node.args[1]
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "self":
                if target.attr not in self.methods:
                    missing.append(target.attr)
        self.assertEqual([], sorted(set(missing)))

    def test_dashboard_reset_contract_exists(self) -> None:
        source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('make_action("Dashboard zurücksetzen", self.reset_dashboard_layout', source)
        self.assertIn("def reset_dashboard_layout", source)
        self.assertIn('self.config.pop("window_geometry", None)', source)
        self.assertIn('self.config["training_details_visible"] = False', source)

    def test_expert_folder_actions_have_targets(self) -> None:
        for method in [
            "open_sessions_folder",
            "open_data_folder",
            "open_log_file",
            "open_debug_folder",
            "open_windows_settings_page",
            "show_display_info",
            "show_shortcuts_dialog",
        ]:
            self.assertIn(method, self.methods)


if __name__ == "__main__":
    unittest.main()
