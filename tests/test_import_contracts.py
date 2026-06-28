"""Import contract tests for local modules.

These tests parse main.py without importing the GUI dependencies. They catch
runtime errors where a local function is moved to another module but main.py
still imports it from the old module.
"""

from __future__ import annotations

import ast
import importlib
import pathlib
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCAL_MODULES = {
    "hrv_core",
    "hrv_sem",
    "hrv_diagnostics",
    "hrv_windows",
    "hrv_security",
    "hrv_ble_strategy",
    "hrv_psychology",
    "hrv_adaptation",
    "hrv_product_contract",
    "hrv_ble_state",
    "hrv_adaptive_ui",
    "hrv_guided_session",
    "hrv_evidence",
    "hrv_ui_capabilities",
    "hrv_visual_feedback",
    "hrv_interaction_design",
}


class LocalImportContractTests(unittest.TestCase):
    def test_main_local_from_imports_exist(self):
        tree = ast.parse((PROJECT_ROOT / "main.py").read_text(encoding="utf-8"))
        missing: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            module_name = node.module
            if module_name not in LOCAL_MODULES:
                continue
            module = importlib.import_module(module_name)
            for alias in node.names:
                if alias.name == "*":
                    continue
                if not hasattr(module, alias.name):
                    missing.append(f"from {module_name} import {alias.name}")

        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
