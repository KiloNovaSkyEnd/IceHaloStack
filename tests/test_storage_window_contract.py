from __future__ import annotations

import inspect
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as app


class StorageWindowContractTest(unittest.TestCase):
    def test_public_class_and_method_contract(self):
        window = app.StorageManagerDialog
        self.assertTrue(issubclass(window, tk.Toplevel))
        self.assertEqual(window.TEMP_PREFIXES, ("icehalostack", "icehalo_", "ihs_"))
        expected = {
            "__init__": ["self", "owner"],
            "_human_size": ["n"],
            "_dir_size": ["path"],
            "_temp_entries": ["tempdir"],
            "_runtime_container": ["current"],
            "_discover_items": ["self"],
            "refresh": ["self"],
            "clean_safe": ["self"],
            "clean_selected": ["self"],
        }
        for name, parameters in expected.items():
            self.assertEqual(
                list(inspect.signature(getattr(window, name)).parameters),
                parameters,
                name,
            )

    def test_stateless_helpers_keep_their_behavior(self):
        window = app.StorageManagerDialog
        self.assertEqual(window._human_size(0), "0 B")
        self.assertEqual(window._human_size(1024), "1 KB")
        self.assertEqual(window._human_size(3 * 1024**2), "3.00 MB")
        self.assertEqual(window._human_size(object()), "—")

        with tempfile.TemporaryDirectory(prefix="ihs_storage_contract_") as tmp:
            root = Path(tmp)
            (root / "plain.txt").write_bytes(b"abc")
            (root / "nested").mkdir()
            (root / "nested" / "data.bin").write_bytes(b"12345")
            (root / "IceHaloStack-cache").mkdir()
            (root / "ihs_job").write_bytes(b"x")
            (root / "unrelated").mkdir()

            self.assertEqual(window._dir_size(root), 9)
            self.assertEqual(
                {p.name for p in window._temp_entries(root)},
                {"IceHaloStack-cache", "ihs_job"},
            )


if __name__ == "__main__":
    unittest.main()
