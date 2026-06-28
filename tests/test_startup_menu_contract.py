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

    def test_update_controls_action_references_are_declared_or_guarded(self) -> None:
        build_menus = next(
            node for node in self.main_window.body if isinstance(node, ast.FunctionDef) and node.name == "_build_menus"
        )
        update_controls = next(
            node for node in self.main_window.body if isinstance(node, ast.FunctionDef) and node.name == "_update_controls"
        )
        declared_actions: set[str] = set()
        for node in ast.walk(build_menus):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                    and target.attr.endswith("_action")
                ):
                    declared_actions.add(target.attr)

        missing: list[str] = []

        def guarded_attrs(test: ast.AST) -> set[str]:
            if (
                isinstance(test, ast.Call)
                and isinstance(test.func, ast.Name)
                and test.func.id == "hasattr"
                and len(test.args) >= 2
                and isinstance(test.args[0], ast.Name)
                and test.args[0].id == "self"
                and isinstance(test.args[1], ast.Constant)
                and isinstance(test.args[1].value, str)
            ):
                return {test.args[1].value}
            if isinstance(test, ast.BoolOp):
                out: set[str] = set()
                for value in test.values:
                    out.update(guarded_attrs(value))
                return out
            return set()

        def visit(node: ast.AST, active_guards: set[str]) -> None:
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "setEnabled"
                and isinstance(node.func.value, ast.Attribute)
                and isinstance(node.func.value.value, ast.Name)
                and node.func.value.value.id == "self"
            ):
                attr = node.func.value.attr
                if attr.endswith("_action") and attr not in declared_actions and attr not in active_guards:
                    missing.append(attr)

            if isinstance(node, ast.If):
                next_guards = active_guards | guarded_attrs(node.test)
                for child in node.body:
                    visit(child, next_guards)
                for child in node.orelse:
                    visit(child, active_guards)
                return

            for child in ast.iter_child_nodes(node):
                visit(child, active_guards)

        visit(update_controls, set())
        self.assertEqual([], sorted(set(missing)))


if __name__ == "__main__":
    unittest.main()
