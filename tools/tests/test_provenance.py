"""Require explicit qualification inputs to reject changed source or patches."""

import json
import tempfile
import unittest
from pathlib import Path

from tools.verify_provenance import verify


class ProvenanceTests(unittest.TestCase):
    def test_incorrect_source_inventory_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            inventory = Path(temporary) / "sources.json"
            inventory.write_text("{}")
            with self.assertRaisesRegex(ValueError, "qualified source inventory"):
                verify(inventory, [])

    def test_changed_exported_patch_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            patch = directory / "repair.patch"
            patch.write_text("changed patch bytes")
            series = directory / "SERIES.json"
            series.write_text(
                json.dumps({"patches": [{"label": "repair", "sha256": "0" * 64}]})
            )
            with self.assertRaisesRegex(ValueError, "patch hash drifted"):
                verify(None, [series])


if __name__ == "__main__":
    unittest.main()
